from __future__ import annotations

from paperrepro.agents.base import spec
from paperrepro.llm import LLM
from paperrepro.state import Caption
from paperrepro.trace import Tracer


def run(description: str, llm: LLM, tracer: Tracer) -> tuple[Caption, int]:
    out, usage = llm.structured(agent="caption_writer", system=spec("caption_writer"),
                                prompt=f"FIGURE:\n{description}", schema=Caption)
    tracer.event("caption_writer", chars=len(out.caption), tokens=usage.total, model=usage.model)
    return out, usage.total
