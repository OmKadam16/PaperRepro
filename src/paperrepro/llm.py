"""One LLM interface. Swap providers or models per agent without touching agents."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

DEFAULT_MODEL = os.environ.get("PAPERREPRO_MODEL", "claude-sonnet-5-5")
# Per-agent override, e.g. PAPERREPRO_MODEL_CODER=claude-opus-5-5
def model_for(agent: str) -> str:
    return os.environ.get(f"PAPERREPRO_MODEL_{agent.upper()}", DEFAULT_MODEL)


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


class LLM(Protocol):
    def structured(self, *, agent: str, system: str, prompt: str, schema: type[T]) -> tuple[T, Usage]:
        ...


class AnthropicLLM:
    """Structured output via forced tool use. Needs ANTHROPIC_API_KEY."""

    def __init__(self) -> None:
        import anthropic

        self.client = anthropic.Anthropic()

    def structured(self, *, agent: str, system: str, prompt: str, schema: type[T]) -> tuple[T, Usage]:
        tool = {
            "name": "submit",
            "description": f"Submit the final {schema.__name__}.",
            "input_schema": schema.model_json_schema(),
        }
        resp = self.client.messages.create(
            model=model_for(agent),
            max_tokens=16000,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            tools=[tool],
            tool_choice={"type": "tool", "name": "submit"},
        )
        block = next(b for b in resp.content if b.type == "tool_use")
        usage = Usage(resp.usage.input_tokens, resp.usage.output_tokens)
        return schema.model_validate(block.input), usage
