"""Deterministic state machine. Routes between agents, enforces budgets, persists state."""
from __future__ import annotations

import time
from pathlib import Path

from paperrepro.agents import (
    coder,
    critic,
    data_finder,
    executor,
    ingestor,
    methods_extractor,
    reporter,
)
from paperrepro.llm import LLM
from paperrepro.state import Route, RunState
from paperrepro.trace import Tracer

# Order of the forward pipeline. A route sends control back to an earlier step,
# then execution continues forward from there.
PIPELINE = ["ingest", "extract", "find_data", "code", "execute", "critic"]
ROUTE_TO_STEP = {
    Route.coder: "code",
    Route.methods_extractor: "extract",
    Route.data_finder: "find_data",
}


def _over_budget(state: RunState) -> str | None:
    b = state.budget
    if state.tokens_used > b.max_tokens:
        return "token budget"
    if time.time() - state.started_at > b.max_seconds:
        return "time budget"
    return None


def run_pipeline(state: RunState, llm: LLM, root: Path) -> RunState:
    tracer = Tracer(state.run_dir(root) / "trace.jsonl")
    tracer.event("orchestrator", start=state.url, dry_run=state.dry_run)
    step_i = 0
    iterations = 0
    try:
        while step_i < len(PIPELINE):
            reason = _over_budget(state)
            if reason:
                state.status = "budget_exhausted"
                state.critic_feedback = f"stopped: {reason}"
                break
            step = PIPELINE[step_i]
            if step == "ingest":
                ingestor.run(state, llm, tracer)
            elif step == "extract":
                methods_extractor.run(state, llm, tracer)
            elif step == "find_data":
                data_finder.run(state, llm, tracer)
            elif step == "code":
                coder.run(state, llm, tracer, root)
            elif step == "execute":
                executor.run(state, tracer, root)
            elif step == "critic":
                critic.run(state, llm, tracer)
                iterations += 1
                if state.route == Route.reporter:
                    break
                if iterations >= state.budget.max_iterations:
                    state.status = "budget_exhausted"
                    tracer.event("orchestrator", stop="iteration budget")
                    break
                step_i = PIPELINE.index(ROUTE_TO_STEP[state.route])
                tracer.event("orchestrator", reroute=state.route.value)
                state.save(root)
                continue
            state.save(root)
            step_i += 1
        if state.status == "running":
            state.status = "done"
    except Exception as e:  # keep the trace and a partial report even on crash
        state.status, state.error = "error", repr(e)
        tracer.event("orchestrator", error=repr(e))
    reporter.run(state, tracer, root)
    state.save(root)
    return state
