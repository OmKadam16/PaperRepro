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

# gpt-6.1-terra ($1 in / $5 out per 1M tokens, Nov 2026) for reading, framing, judging and
# captions; gpt-6.2-sol ($2 / $10) where the reasoning is the product: mapping a literature
# into gaps, and peer review. A typical gap study or review costs a few cents to ~$0.10.
# Override per agent with PAPERREPRO_MODEL_<AGENT>, or all with PAPERREPRO_MODEL.
OPENAI_DEFAULT = "gpt-6.1-terra"
OPENAI_DEFAULTS = {"ocr": "gpt-6.1-terra", "claim_finder": "gpt-6.1-terra", "source_judge": "gpt-6.1-terra",
                   "idea_framer": "gpt-6.1-terra", "gap_analyst": "gpt-6.2-sol", "novelty_checker": "gpt-6.1-terra",
                   "reviewer": "gpt-6.2-sol", "caption_writer": "gpt-6.1-terra", "research_guide": "gpt-6.1-terra"}
OPENAI_EFFORT = {"ocr": "low", "claim_finder": "low", "source_judge": "medium", "idea_framer": "low",
                 "gap_analyst": "medium", "novelty_checker": "medium", "reviewer": "medium", "caption_writer": "low", "research_guide": "low"}
ANTHROPIC_DEFAULT = "claude-sonnet-5-5"


def model_for(agent: str, provider_default: str) -> str:
    return (os.environ.get(f"PAPERREPRO_MODEL_{agent.upper()}")
            or os.environ.get("PAPERREPRO_MODEL") or provider_default)


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""  # which model answered; recorded in the trace

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens

    def __add__(self, other: Usage) -> Usage:
        return Usage(self.input_tokens + other.input_tokens, self.output_tokens + other.output_tokens,
                     self.model or other.model)


class LLM(Protocol):
    def structured(self, *, agent: str, system: str, prompt: str, schema: type[T],
                   image_png: bytes | None = None) -> tuple[T, Usage]:
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


def _b64(data: bytes) -> str:
    import base64

    return base64.b64encode(data).decode()


def _openai_input(prompt: str, image_png: bytes | None):
    if image_png is None:
        return prompt
    return [{"role": "user", "content": [
        {"type": "input_text", "text": prompt},
        {"type": "input_image", "image_url": f"data:image/png;base64,{_b64(image_png)}"}]}]


def _anthropic_content(prompt: str, image_png: bytes | None):
    if image_png is None:
        return prompt
    return [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": _b64(image_png)}},
            {"type": "text", "text": prompt}]


class OpenAILLM:
    """Structured output via a forced function call on the Responses API. Needs OPENAI_API_KEY."""

    def __init__(self) -> None:
        try:
            import openai
        except ImportError as e:
            raise LLMError("OpenAI provider needs: uv pip install -e '.[openai]'") from e
        self.client = openai.OpenAI(max_retries=3, timeout=600)

    def structured(self, *, agent: str, system: str, prompt: str, schema: type[T],
                   image_png: bytes | None = None) -> tuple[T, Usage]:
        model = model_for(agent, OPENAI_DEFAULTS.get(agent, OPENAI_DEFAULT))
        effort = os.environ.get(f"PAPERREPRO_EFFORT_{agent.upper()}", OPENAI_EFFORT.get(agent, "medium"))
        tool = {"type": "function", "name": "submit", "strict": False,
                "description": f"Submit the final {schema.__name__}.",
                "parameters": schema.model_json_schema()}

        def call(p: str) -> tuple[dict, Usage]:
            resp = self.client.responses.create(
                model=model, instructions=system, input=_openai_input(p, image_png), tools=[tool],
                tool_choice={"type": "function", "name": "submit"},
                reasoning={"effort": effort}, max_output_tokens=64000,
            )
            fc = next((o for o in resp.output if o.type == "function_call"), None)
            u = Usage(resp.usage.input_tokens, resp.usage.output_tokens, model) if resp.usage else Usage(model=model)
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

    def structured(self, *, agent: str, system: str, prompt: str, schema: type[T],
                   image_png: bytes | None = None) -> tuple[T, Usage]:
        tool = {"name": "submit", "description": f"Submit the final {schema.__name__}.",
                "input_schema": schema.model_json_schema()}

        def call(p: str) -> tuple[dict, Usage]:
            model = model_for(agent, ANTHROPIC_DEFAULT)
            resp = self.client.messages.create(
                model=model, max_tokens=16000, system=system,
                messages=[{"role": "user", "content": _anthropic_content(p, image_png)}], tools=[tool],
                tool_choice={"type": "tool", "name": "submit"},
            )
            block = next(b for b in resp.content if b.type == "tool_use")
            return block.input, Usage(resp.usage.input_tokens, resp.usage.output_tokens, model)

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
