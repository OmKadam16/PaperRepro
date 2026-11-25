"""Static HTML viewer for one run: `paperrepro view runs/<id>` -> runs/<id>/view.html.

Reads only state.json and trace.jsonl. All numbers shown come from those files.
The page is self-contained (no server); data is embedded as JSON and rendered with
textContent only, so LLM-written text can never inject markup.
"""
from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path

from paperrepro.agents.reporter import _finished_at, supplementary
from paperrepro.state import RunState

STATIONS = ["ingestor", "methods_extractor", "data_finder", "coder", "executor", "critic", "reporter"]


def _events(trace: Path) -> list[dict]:
    if not trace.exists():
        return []
    out = []
    for ln in trace.read_text().splitlines():
        if ln.strip():
            out.append(json.loads(ln))
    return out


def _summary(e: dict) -> str:
    a = e.get("agent")
    if a == "ingestor":
        return f"read {e.get('chars', '?')} chars as {e.get('kind', '?')}, {e.get('sections', '?')} sections"
    if a == "methods_extractor":
        return f"{e.get('claims', '?')} claims, {e.get('ambiguities', '?')} assumptions logged"
    if a == "data_finder":
        ds = e.get("datasets", [])
        got = sum(1 for d in ds if isinstance(d, dict) and d.get("local_paths"))
        return f"{got} of {len(ds)} files downloaded"
    if a == "coder":
        return f"attempt {e.get('attempt')}: wrote {', '.join(e.get('files', []))}"
    if a == "executor":
        if e.get("timed_out"):
            return f"attempt {e.get('attempt')}: timed out"
        code = e.get("exit_code")
        tail = (e.get("stderr_tail") or "").strip()
        if code == 0:
            return f"attempt {e.get('attempt')}: ran in {e.get('duration_s')}s, {len(e.get('metrics') or {})} metrics"
        first = tail.splitlines()[0] if tail else ""
        return f"attempt {e.get('attempt')}: exit {code}. {first[:160]}"
    if a == "critic":
        rule = e.get("rule")
        return (f"rule {rule}: " if rule else "") + (e.get("explanation") or f"route {e.get('route')}")
    if a == "reporter":
        return "report written"
    return json.dumps({k: v for k, v in e.items() if k not in ("t", "agent")})[:200]


def build_data(run_dir: Path) -> dict:
    state = RunState.load(run_dir / "state.json")
    events = _events(run_dir / "trace.jsonl")
    t0 = state.started_at
    steps, lap = [], 0
    for e in events:
        if e.get("agent") == "orchestrator":
            if "reroute" in e:
                lap += 1
                steps.append({"kind": "reroute", "to": e["reroute"], "lap": lap, "t": e["t"] - t0})
            continue
        if e.get("agent") in STATIONS:
            ok = None
            if e["agent"] == "executor":
                ok = e.get("exit_code") == 0 and not e.get("timed_out")
            steps.append({"kind": "step", "agent": e["agent"], "lap": lap, "t": round(e["t"] - t0, 1),
                          "summary": _summary(e), "ok": ok, "route": e.get("route")})
    claims = {c.id: c for c in state.spec.claims} if state.spec else {}
    verdicts = []
    for v in state.verdicts:
        c = claims.get(v.claim_id)
        tol = None
        if c:
            tol = c.tolerance if c.tolerance_type == "abs" else c.tolerance * abs(c.paper_value)
        verdicts.append({"id": v.claim_id, "paper": v.paper_value, "measured": v.measured_value,
                         "tol": tol, "status": v.status.value, "source": c.source if c else "",
                         "metric": c.metric if c else "", "diagnosis": v.diagnosis})
    end = _finished_at(run_dir / "trace.jsonl")  # ignores later re-renders
    return {
        "title": state.paper.title if state.paper else state.url, "url": state.url,
        "run_id": state.run_id, "status": state.status, "attempts": state.attempt,
        "tokens": state.tokens_used, "wall_s": round(end - t0, 1), "dry_run": state.dry_run,
        "error": state.error, "stations": STATIONS, "steps": steps, "verdicts": verdicts,
        "supplementary": supplementary(state),
        "datasets": [{"name": d.name, "status": d.status, "verified": d.verified,
                      "size_mb": d.size_mb, "note": d.verify_note} for d in state.datasets],
        "ambiguities": state.spec.ambiguities if state.spec else [],
    }


def render(data: dict) -> str:
    template = files("paperrepro").joinpath("viewer_template.html").read_text()
    blob = json.dumps(data).replace("</", "<\\/")  # cannot close the <script> tag
    return template.replace("/*__RUN_DATA__*/null", blob)


def write(run_dir: Path) -> Path:
    out = run_dir / "view.html"
    out.write_text(render(build_data(run_dir)))
    return out
