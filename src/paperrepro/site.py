"""Static web app over all runs: `paperrepro site` -> runs/_site/*.html.

Pages: index (the Lab dashboard), claims (every claim, filterable), crew (the agents),
and one run-<id>.html per run. Everything is read from each run's state.json and
trace.jsonl plus agents/*.md; no number is computed or typed anywhere else. Data is
embedded as JSON and rendered with textContent only, so LLM text cannot inject markup.
"""
from __future__ import annotations

import json
import time
from collections import Counter
from importlib.resources import files
from pathlib import Path

from paperrepro.agents.base import AGENTS_DIR
from paperrepro.agents.reporter import _finished_at, supplementary
from paperrepro.llm import OPENAI_DEFAULTS
from paperrepro.state import RunState

STATIONS = ["ingestor", "methods_extractor", "data_finder", "coder", "executor", "critic", "reporter"]
CREW = [  # (agent, friendly name, uses an LLM)
    ("ingestor", "The Reader", True),
    ("methods_extractor", "The Note-taker", True),
    ("data_finder", "The Data Hunter", True),
    ("coder", "The Coder", True),
    ("executor", "The Runner", False),
    ("critic", "The Judge", True),
    ("reporter", "The Scribe", False),
]
SITE_DIR = "_site"
FINISHED = ("done", "budget_exhausted")  # runs whose verdicts are final
STALE_S = 1800  # a "running" run with no trace event for this long was interrupted


# ---------------------------------------------------------------- reading runs
def list_runs(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(p for p in root.iterdir() if p.is_dir() and (p / "state.json").exists())


def _events(trace: Path) -> list[dict]:
    if not trace.exists():
        return []
    return [json.loads(ln) for ln in trace.read_text().splitlines() if ln.strip()]


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
        if e.get("exit_code") == 0:
            return f"attempt {e.get('attempt')}: ran in {e.get('duration_s')}s, {len(e.get('metrics') or {})} metrics"
        tail = (e.get("stderr_tail") or "").strip()
        return f"attempt {e.get('attempt')}: exit {e.get('exit_code')}. {(tail.splitlines() or [''])[0][:160]}"
    if a == "critic":
        rule = e.get("rule")
        return (f"rule {rule}: " if rule else "") + (e.get("explanation") or f"route {e.get('route')}")
    if a == "reporter":
        return "report written"
    return ""


def _when(t: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(t))


def _verdicts(state: RunState) -> list[dict]:
    claims = {c.id: c for c in state.spec.claims} if state.spec else {}
    sup = supplementary(state)
    out = []
    for v in state.verdicts:
        c = claims.get(v.claim_id)
        tol = None
        if c:
            tol = c.tolerance if c.tolerance_type == "abs" else c.tolerance * abs(c.paper_value)
        off = None
        if v.measured_value is not None and tol:
            off = round(abs(v.measured_value - v.paper_value) / tol, 2)
        ghosts = [{"label": k.split("@", 1)[1], "val": val} for k, val in sup.items()
                  if k.startswith(v.claim_id + "@")]
        out.append({"id": v.claim_id, "paper": v.paper_value, "measured": v.measured_value,
                    "tol": tol, "off": off, "status": v.status.value,
                    "source": c.source if c else "", "metric": c.metric if c else "",
                    "diagnosis": v.diagnosis, "ghosts": ghosts})
    return out


def load_run(run_dir: Path) -> dict:
    """Everything the pages need about one run."""
    state = RunState.load(run_dir / "state.json")
    events = _events(run_dir / "trace.jsonl")
    t0 = state.started_at
    steps, lap, models = [], 0, Counter()
    calls, tokens = Counter(), Counter()
    for e in events:
        a = e.get("agent")
        if a == "orchestrator":
            if "reroute" in e:
                lap += 1
                steps.append({"kind": "reroute", "to": e["reroute"], "lap": lap})
            continue
        if a not in STATIONS:
            continue
        if a == "reporter" and any(s.get("agent") == "reporter" for s in steps):
            continue  # later re-renders of the report are not part of the run
        ok = (e.get("exit_code") == 0 and not e.get("timed_out")) if a == "executor" else None
        steps.append({"kind": "step", "agent": a, "lap": lap, "t": round(e["t"] - t0, 1),
                      "summary": _summary(e), "ok": ok, "model": e.get("model", "")})
        calls[a] += 1
        tokens[a] += int(e.get("tokens") or 0)
        if e.get("model"):
            models[e["model"]] += 1
    verdicts = _verdicts(state)
    counts = Counter(v["status"] for v in verdicts)
    end = _finished_at(run_dir / "trace.jsonl")
    status = state.status
    if status == "running" and time.time() - end > STALE_S:
        status = "interrupted"  # the process was stopped; this is not a live run
    return {
        "id": state.run_id, "title": state.paper.title if state.paper else state.url,
        "url": state.url, "status": status, "dry_run": state.dry_run, "error": state.error,
        "finished": status in FINISHED, "started": t0,
        "when": _when(t0), "attempts": state.attempt, "tokens": state.tokens_used,
        "wall_s": round(end - t0, 1),
        "routes": [r.value for r in state.route_history], "models": sorted(models),
        "counts": dict(counts), "n_claims": len(verdicts), "verdicts": verdicts,
        "steps": steps, "stations": STATIONS, "agent_calls": dict(calls), "agent_tokens": dict(tokens),
        "datasets": [{"name": d.name, "status": d.status, "verified": d.verified,
                      "size_mb": d.size_mb, "note": d.verify_note} for d in state.datasets],
        "ambiguities": state.spec.ambiguities if state.spec else [],
    }


def _brief(r: dict) -> dict:
    keep = ("id", "title", "url", "status", "dry_run", "error", "finished", "when", "attempts", "tokens",
            "wall_s", "routes", "models", "counts", "n_claims")
    b = {k: r[k] for k in keep}
    b["glyphs"] = [{"id": v["id"], "status": v["status"], "off": v["off"]} for v in r["verdicts"]]
    return b


def crew(runs: list[dict]) -> list[dict]:
    out = []
    for agent, name, uses_llm in CREW:
        spec_path = AGENTS_DIR / f"{agent}.md"
        models = Counter()
        for r in runs:
            for s in r["steps"]:
                if s.get("agent") == agent and s.get("model"):
                    models[s["model"]] += 1
        real = [r for r in runs if not r["dry_run"]]
        out.append({
            "agent": agent, "name": name, "llm": uses_llm,
            "default_model": OPENAI_DEFAULTS.get(agent) if uses_llm else None,
            "spec": spec_path.read_text() if spec_path.exists() else "",
            "calls": sum(r["agent_calls"].get(agent, 0) for r in real),
            "tokens": sum(r["agent_tokens"].get(agent, 0) for r in real),
            "models_used": dict(models),
            "sent_back_to": sum(r["routes"].count(agent) for r in real),
        })
    return out


# ---------------------------------------------------------------- rendering
def _page(template: str, data: dict) -> str:
    blob = json.dumps(data).replace("</", "<\\/")  # cannot close the <script> tag
    return template.replace("/*__RUN_DATA__*/null", blob)


def build_site(root: Path) -> Path:
    """Write the whole site under root/_site and return the index path."""
    out = root / SITE_DIR
    out.mkdir(parents=True, exist_ok=True)
    template = files("paperrepro").joinpath("site_template.html").read_text()
    runs = sorted((load_run(d) for d in list_runs(root)), key=lambda r: r["started"])
    briefs = [_brief(r) for r in runs]
    nav = {"runs": [{"id": b["id"], "when": b["when"], "dry_run": b["dry_run"]} for b in briefs]}
    (out / "index.html").write_text(_page(template, {"page": "lab", "nav": nav, "runs": briefs}))
    claims = [{**v, "run": r["id"], "title": r["title"], "when": r["when"]}
              for r in runs if not r["dry_run"] and r["finished"] for v in r["verdicts"]]
    (out / "claims.html").write_text(_page(template, {"page": "claims", "nav": nav, "claims": claims}))
    (out / "crew.html").write_text(_page(template, {"page": "crew", "nav": nav, "crew": crew(runs)}))
    for i, r in enumerate(runs):
        prev_id = runs[i - 1]["id"] if i > 0 else None
        next_id = runs[i + 1]["id"] if i + 1 < len(runs) else None
        (out / f"run-{r['id']}.html").write_text(_page(
            template, {"page": "run", "nav": nav, "run": r, "prev": prev_id, "next": next_id}))
    return out / "index.html"
