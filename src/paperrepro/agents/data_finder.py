from __future__ import annotations

from paperrepro.agents.base import spec
from paperrepro.llm import LLM
from paperrepro.state import DatasetList, RunState
from paperrepro.trace import Tracer


def run(state: RunState, llm: LLM, tracer: Tracer) -> None:
    assert state.spec and state.paper, "extract first"
    prompt = (
        f"DATASETS MENTIONED: {state.spec.datasets}\n"
        f"DATA LINKS IN PAPER: {state.paper.data_links}\n"
    )
    if state.critic_feedback:
        prompt += f"\nCRITIC FEEDBACK:\n{state.critic_feedback}"
    result, usage = llm.structured(
        agent="data_finder", system=spec("data_finder"), prompt=prompt, schema=DatasetList
    )
    state.datasets = result.items
    state.tokens_used += usage.total
    tracer.event("data_finder", datasets=[d.name for d in result.items], tokens=usage.total)
    # TODO(phase1): verify each URL resolves and size is within budget before download.
