"""One LLM interface. Swap providers or models per agent without touching agents.

Provider: PAPERREPRO_PROVIDER=openai|anthropic (default: whichever API key is set, OpenAI first).
Model per agent: PAPERREPRO_MODEL_<AGENT>=..., else PAPERREPRO_MODEL, else the provider default.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Protocol, TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)

# Cheap model for mechanical agents, the cheapest flagship where quality decides the result.
# Prices (Nov 2026, per 1M tokens in/out): gpt-6.1-terra $1/$5, gpt-6.2-sol $2/$10.
# (Run 3 on gpt-5-mini everywhere picked fewer claims and a weaker protocol; not worth the saving.)
# Override per agent with PAPERREPRO_MODEL_<AGENT>, or all agents with PAPERREPRO_MODEL.
OPENAI_DEFAULT = "gpt-6.2-sol"
OPENAI_DEFAULTS = {
    "ingestor": "gpt-6.1-terra",
    "data_finder": "gpt-6.1-terra",
    "methods_extractor": "gpt-6.2-sol",
    "coder": "gpt-6.2-sol",
    "critic": "gpt-6.2-sol",
}
OPENAI_EFFORT = {"ingestor": "low", "data_finder": "low", "critic": "low"}  # others: medium
ANTHROPIC_DEFAULT = "claude-sonnet-5-5"


def model_for(agent: str, provider_default: str) -> str:
    return (os.environ.get(f"PAPERREPRO_MODEL_{agent.upper()}")
            or os.environ.get("PAPERREPRO_MODEL") or provider_default)


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens

    def __add__(self, other: Usage) -> Usage:
        return Usage(self.input_tokens + other.input_tokens, self.output_tokens + other.output_tokens)


class LLM(Protocol):
    def structured(self, *, agent: str, system: str, prompt: str, schema: type[T]) -> tuple[T, Usage]:
        ...


class LLMError(RuntimeError):
    pass


def _validate_with_retry(call, schema: type[T], prompt: str) -> tuple[T, Usage]:
    """call(prompt) -> (raw_args_dict, Usage). Re-ask once if the output fails validation."""
    raw, usage = call(prompt)
    try:
        return schema.model_validate(raw), usage
    except ValidationError as e:
        retry = (f"{prompt}\n\nYOUR PREVIOUS SUBMISSION FAILED SCHEMA VALIDATION:\n{e}\n"
                 "Submit again, fixing exactly these errors.")
        raw, u2 = call(retry)
        try:
            return schema.model_validate(raw), usage + u2
        except ValidationError as e2:
            raise LLMError(f"{schema.__name__} invalid after retry: {e2}") from e2


class OpenAILLM:
    """Structured output via a forced function call on the Responses API. Needs OPENAI_API_KEY."""

    def __init__(self) -> None:
        try:
            import openai
        except ImportError as e:
            raise LLMError("OpenAI provider needs: uv pip install -e '.[openai]'") from e
        self.client = openai.OpenAI(max_retries=3, timeout=600)

    def structured(self, *, agent: str, system: str, prompt: str, schema: type[T]) -> tuple[T, Usage]:
        model = model_for(agent, OPENAI_DEFAULTS.get(agent, OPENAI_DEFAULT))
        effort = os.environ.get(f"PAPERREPRO_EFFORT_{agent.upper()}", OPENAI_EFFORT.get(agent, "medium"))
        tool = {"type": "function", "name": "submit", "strict": False,
                "description": f"Submit the final {schema.__name__}.",
                "parameters": schema.model_json_schema()}

        def call(p: str) -> tuple[dict, Usage]:
            resp = self.client.responses.create(
                model=model, instructions=system, input=p, tools=[tool],
                tool_choice={"type": "function", "name": "submit"},
                reasoning={"effort": effort}, max_output_tokens=64000,
            )
            fc = next((o for o in resp.output if o.type == "function_call"), None)
            u = Usage(resp.usage.input_tokens, resp.usage.output_tokens) if resp.usage else Usage()
            if fc is None:
                raise LLMError(f"{agent}: {model} returned no function call (status={resp.status}, "
                               f"incomplete={getattr(resp, 'incomplete_details', None)})")
            try:
                return json.loads(fc.arguments), u
            except json.JSONDecodeError as e:
                raise LLMError(f"{agent}: {model} returned malformed JSON arguments: {e}") from e

        return _validate_with_retry(call, schema, prompt)


class AnthropicLLM:
    """Structured output via forced tool use. Needs ANTHROPIC_API_KEY."""

    def __init__(self) -> None:
        import anthropic

        self.client = anthropic.Anthropic()

    def structured(self, *, agent: str, system: str, prompt: str, schema: type[T]) -> tuple[T, Usage]:
        tool = {"name": "submit", "description": f"Submit the final {schema.__name__}.",
                "input_schema": schema.model_json_schema()}

        def call(p: str) -> tuple[dict, Usage]:
            resp = self.client.messages.create(
                model=model_for(agent, ANTHROPIC_DEFAULT), max_tokens=16000, system=system,
                messages=[{"role": "user", "content": p}], tools=[tool],
                tool_choice={"type": "tool", "name": "submit"},
            )
            block = next(b for b in resp.content if b.type == "tool_use")
            return block.input, Usage(resp.usage.input_tokens, resp.usage.output_tokens)

        return _validate_with_retry(call, schema, prompt)


def make_llm(provider: str | None = None) -> LLM:
    provider = provider or os.environ.get("PAPERREPRO_PROVIDER")
    if not provider:
        if os.environ.get("OPENAI_API_KEY"):
            provider = "openai"
        elif os.environ.get("ANTHROPIC_API_KEY"):
            provider = "anthropic"
        else:
            raise LLMError("no API key: set OPENAI_API_KEY or ANTHROPIC_API_KEY (or use --dry-run)")
    if provider == "openai":
        return OpenAILLM()
    if provider == "anthropic":
        return AnthropicLLM()
    raise LLMError(f"unknown provider {provider!r}; use openai or anthropic")
