from __future__ import annotations

from pathlib import Path

from paperrepro.agents.coder import workspace_dir
from paperrepro.state import RunState
from paperrepro.tools.sandbox import run_workspace
from paperrepro.trace import Tracer


def run(state: RunState, tracer: Tracer, root: Path) -> None:
    ws = workspace_dir(state, root)
    # stale metrics from a previous attempt must never be read as this attempt's output
    stale = ws / "results" / "metrics.json"
    if stale.exists():
        stale.unlink()
    res = run_workspace(
        ws, timeout_s=state.budget.exec_timeout_s, mem_mb=state.budget.exec_memory_mb,
        install_deps=not state.dry_run,
    )
    state.exec_result = res
    tracer.event("executor", exit_code=res.exit_code, duration_s=res.duration_s,
                 metrics=res.metrics, timed_out=res.timed_out)
