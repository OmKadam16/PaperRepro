from __future__ import annotations

from pathlib import Path

from paperrepro.agents.base import spec
from paperrepro.llm import LLM
from paperrepro.state import CodeBundle, RunState
from paperrepro.trace import Tracer


def workspace_dir(state: RunState, root: Path) -> Path:
    return state.run_dir(root) / "workspace"


def run(state: RunState, llm: LLM, tracer: Tracer, root: Path) -> None:
    assert state.spec, "extract first"
    state.attempt += 1
    prompt = (
        f"ATTEMPT: {state.attempt}\n"
        f"SPEC:\n{state.spec.model_dump_json()}\n"
        f"DATASETS:\n{[d.model_dump() for d in state.datasets]}\n"
    )
    if state.exec_result:
        prompt += f"\nPREVIOUS RUN:\n{state.exec_result.model_dump_json()}\n"
    if state.critic_feedback:
        prompt += f"\nCRITIC FEEDBACK:\n{state.critic_feedback}\n"
    bundle, usage = llm.structured(agent="coder", system=spec("coder"), prompt=prompt, schema=CodeBundle)

    ws = workspace_dir(state, root)
    ws.mkdir(parents=True, exist_ok=True)
    for rel, content in bundle.files.items():
        p = (ws / rel).resolve()
        if ws.resolve() not in p.parents:  # block path escape
            raise ValueError(f"unsafe path from coder: {rel}")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    (ws / "results").mkdir(exist_ok=True)
    state.tokens_used += usage.total
    tracer.event("coder", attempt=state.attempt, files=sorted(bundle.files), tokens=usage.total)
