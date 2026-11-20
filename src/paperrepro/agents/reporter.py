from __future__ import annotations

import json
import time
from pathlib import Path

from paperrepro.state import RunState
from paperrepro.trace import Tracer


def render(state: RunState) -> str:
    title = state.paper.title if state.paper else state.url
    lines = [f"# Reproduction report: {title}", "", f"Source: {state.url}",
             f"Run: `{state.run_id}`  |  attempts: {state.attempt}  |  tokens: {state.tokens_used}"
             f"  |  wall-clock: {round(time.time() - state.started_at, 1)}s", ""]
    if state.dry_run:
        lines += ["> **DRY RUN.** Synthetic agent outputs to test the plumbing. "
                  "Nothing here reflects a real paper.", ""]
    lines += ["| Claim | Paper | Measured | Delta | Verdict |", "|---|---|---|---|---|"]
    for v in state.verdicts:
        m = "n/a" if v.measured_value is None else f"{v.measured_value:g}"
        d = "n/a" if v.delta is None else f"{v.delta:+g}"
        lines.append(f"| {v.claim_id} | {v.paper_value:g} | {m} | {d} | {v.status.value} |")
    notes = [f"- {v.claim_id}: {v.diagnosis}" for v in state.verdicts if v.diagnosis]
    if notes:
        lines += ["", "## Notes", *notes]
    if state.spec and state.spec.ambiguities:
        lines += ["", "## Assumptions / ambiguities", *[f"- {a}" for a in state.spec.ambiguities]]
    lines += ["", f"Status: {state.status}"]
    return "\n".join(lines) + "\n"


def run(state: RunState, tracer: Tracer, root: Path) -> None:
    d = state.run_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    (d / "report.md").write_text(render(state))
    (d / "report.json").write_text(json.dumps(
        {"run_id": state.run_id, "url": state.url, "dry_run": state.dry_run,
         "attempts": state.attempt, "verdicts": [v.model_dump(mode="json") for v in state.verdicts]},
        indent=2))
    tracer.event("reporter", path=str(d / "report.md"))
