"""Deterministic report from RunState. No LLM, so no number can be altered on the way out."""
from __future__ import annotations

import json
import time
from pathlib import Path

from paperrepro.state import RunState
from paperrepro.trace import Tracer


def _fmt(x: float | None, sign: bool = False) -> str:
    if x is None:
        return "n/a"
    return f"{x:+.4g}" if sign else f"{x:.4g}"


def supplementary(state: RunState) -> dict[str, float]:
    """Executor metrics that are not claim ids: shown for transparency, never used for verdicts."""
    if not state.exec_result or not state.spec:
        return {}
    ids = {c.id for c in state.spec.claims}
    return {k: v for k, v in state.exec_result.metrics.items() if k not in ids}


def _finished_at(trace: Path) -> float:
    """Last trace event time: a re-rendered report must not count time since the run ended."""
    if trace.exists():
        lines = [ln for ln in trace.read_text().splitlines() if ln.strip()]
        ends = [json.loads(ln)["t"] for ln in lines if json.loads(ln).get("agent") != "reporter"]
        if ends:
            return ends[-1]
    return time.time()


def render(state: RunState, finished_at: float | None = None) -> str:
    title = state.paper.title if state.paper else state.url
    wall = round((finished_at or time.time()) - state.started_at, 1)
    lines = [f"# Reproduction report: {title}", "", f"Source: {state.url}",
             f"Run: `{state.run_id}`  |  status: **{state.status}**  |  attempts: {state.attempt}  |  "
             f"tokens: {state.tokens_used}  |  wall-clock: {wall}s",
             f"Route history: {' -> '.join(r.value for r in state.route_history) or 'none'}  |  "
             "trace: `trace.jsonl`", ""]
    if state.dry_run:
        lines += ["> **DRY RUN.** Synthetic agent outputs to test the plumbing. "
                  "Nothing here reflects a real paper.", ""]
    if state.error:
        lines += [f"> **Run error:** `{state.error}`", ""]

    claims = {c.id: c for c in state.spec.claims} if state.spec else {}
    lines += ["## Verdicts", "",
              "Measured values come only from the Executor's `results/metrics.json` for the final attempt.", "",
              "| Claim | Source | Paper | Tolerance | Measured | Delta | Verdict |",
              "|---|---|---|---|---|---|---|"]
    for v in state.verdicts:
        c = claims.get(v.claim_id)
        tol = "n/a" if not c else (f"±{c.tolerance:g}" if c.tolerance_type == "abs" else f"±{c.tolerance:.0%}")
        lines.append(f"| {v.claim_id} | {c.source if c else ''} | {v.paper_value:g} | {tol} | "
                     f"{_fmt(v.measured_value)} | {_fmt(v.delta, sign=True)} | **{v.status.value}** |")
    counts: dict[str, int] = {}
    for v in state.verdicts:
        counts[v.status.value] = counts.get(v.status.value, 0) + 1
    lines += ["", "Summary: " + (", ".join(f"{n} {k}" for k, n in counts.items()) or "no verdicts")]

    # one copy of each distinct diagnosis, with the claims it applies to
    diag: dict[str, list[str]] = {}
    for v in state.verdicts:
        if v.diagnosis:
            diag.setdefault(v.diagnosis, []).append(v.claim_id)
    if diag:
        lines += ["", "## Diagnosis"]
        for text, ids in diag.items():
            lines += ["", f"Applies to: {', '.join(ids)}", "", text]

    if sup := supplementary(state):
        lines += ["", "## Supplementary measurements (not used for verdicts)", "",
                  "Values the run measured beyond the claims, such as sensitivity analyses that deviate "
                  "from the paper's stated protocol. They are listed for transparency only.", "",
                  "| Key | Measured |", "|---|---|", *[f"| {k} | {_fmt(v)} |" for k, v in sup.items()]]

    if state.datasets:
        lines += ["", "## Data", "", "| Dataset | Status | Verified | Note |", "|---|---|---|---|"]
        for d in state.datasets:
            sub = " (substitute)" if d.is_substitute else ""
            lines.append(f"| {d.name}{sub} | {d.status} | {'yes' if d.verified else 'no'} | "
                         f"{d.verify_note or d.url} |")

    if state.spec and state.spec.ambiguities:
        lines += ["", "## Assumptions / ambiguities", *[f"- {a}" for a in state.spec.ambiguities]]
    if state.paper and state.paper.notes:
        lines += ["", "## Ingestion notes", *[f"- {n}" for n in state.paper.notes.splitlines() if n]]
    return "\n".join(lines) + "\n"


def run(state: RunState, tracer: Tracer, root: Path) -> None:
    d = state.run_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    (d / "report.md").write_text(render(state, _finished_at(d / "trace.jsonl")))
    (d / "report.json").write_text(json.dumps(
        {"run_id": state.run_id, "url": state.url, "dry_run": state.dry_run, "status": state.status,
         "attempts": state.attempt, "tokens": state.tokens_used,
         "route_history": [r.value for r in state.route_history],
         "verdicts": [v.model_dump(mode="json") for v in state.verdicts],
         "supplementary_metrics": supplementary(state)}, indent=2))
    tracer.event("reporter", path=str(d / "report.md"))
