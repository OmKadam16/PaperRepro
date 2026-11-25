from __future__ import annotations

from paperrepro.agents.base import spec
from paperrepro.llm import LLM
from paperrepro.state import Framing
from paperrepro.trace import Tracer


def run(idea: str, llm: LLM, tracer: Tracer) -> tuple[Framing, int]:
    out, usage = llm.structured(agent="idea_framer", system=spec("idea_framer"),
                                prompt=f"IDEA:\n{idea}", schema=Framing)
    out.questions = [q.strip() for q in out.questions if q.strip()][:4]
    out.queries = [q.strip() for q in out.queries if q.strip()][:6]
    tracer.event("idea_framer", questions=len(out.questions), queries=out.queries,
                 tokens=usage.total, model=usage.model)
    return out, usage.total
