from __future__ import annotations

from paperrepro.agents.base import spec
from paperrepro.llm import LLM
from paperrepro.state import ReproSpec, RunState
from paperrepro.trace import Tracer


def run(state: RunState, llm: LLM, tracer: Tracer) -> None:
    assert state.paper, "ingest first"
    prompt = f"PAPER:\n{state.paper.model_dump_json()}"
    if state.critic_feedback:
        prompt += f"\n\nCRITIC FEEDBACK (re-read the paper for missed details):\n{state.critic_feedback}"
    result, usage = llm.structured(
        agent="methods_extractor", system=spec("methods_extractor"), prompt=prompt, schema=ReproSpec
    )
    state.spec = result
    state.tokens_used += usage.total
    tracer.event("methods_extractor", claims=len(result.claims),
                 ambiguities=len(result.ambiguities), tokens=usage.total)
