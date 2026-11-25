from __future__ import annotations

from paperrepro.agents.base import spec
from paperrepro.llm import LLM
from paperrepro.state import ReproSpec, RunState
from paperrepro.trace import Tracer


def run(state: RunState, llm: LLM, tracer: Tracer) -> None:
    assert state.paper, "ingest first"
    b = state.budget
    prompt = (
        f"COMPUTE BUDGET: CPU only, main.py must finish in {b.exec_timeout_s}s, "
        f"{b.exec_memory_mb} MB RAM, {b.max_data_mb} MB of data in total.\n\n"
        f"PAPER:\n{state.paper.model_dump_json()}"
    )
    if state.user_request:
        prompt += (f"\n\nUSER REQUEST (scopes which claims to choose; never changes values, "
                   f"tolerances or how claims are judged):\n{state.user_request}")
    if state.critic_feedback:
        prompt += f"\n\nCRITIC FEEDBACK (re-read the paper for missed details):\n{state.critic_feedback}"
    result, usage = llm.structured(
        agent="methods_extractor", system=spec("methods_extractor"), prompt=prompt, schema=ReproSpec
    )
    state.spec = result
    state.tokens_used += usage.total
    tracer.event("methods_extractor", claims=len(result.claims),
                 ambiguities=len(result.ambiguities), tokens=usage.total, model=usage.model)
