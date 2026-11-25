from __future__ import annotations

from pathlib import Path

from paperrepro.agents.base import spec
from paperrepro.llm import LLM
from paperrepro.state import (
    Claim,
    Diagnosis,
    ExecResult,
    Route,
    RunState,
    Verdict,
    VerdictStatus,
)
from paperrepro.trace import Tracer

CODE_CHARS = 30_000


def within_tolerance(claim: Claim, measured: float) -> bool:
    delta = abs(measured - claim.paper_value)
    limit = claim.tolerance * abs(claim.paper_value) if claim.tolerance_type == "rel" else claim.tolerance
    return delta <= limit


def compare_claims(claims: list[Claim], res: ExecResult) -> list[Verdict]:
    """Deterministic. Measured values come only from Executor output."""
    out: list[Verdict] = []
    for c in claims:
        if not c.feasible:
            out.append(Verdict(claim_id=c.id, status=VerdictStatus.unverifiable,
                               paper_value=c.paper_value, diagnosis=c.infeasible_reason))
            continue
        if c.id not in res.metrics:
            out.append(Verdict(claim_id=c.id, status=VerdictStatus.failed,
                               paper_value=c.paper_value, diagnosis="no measured value produced"))
            continue
        m = res.metrics[c.id]
        ok = within_tolerance(c, m)
        out.append(Verdict(
            claim_id=c.id, status=VerdictStatus.reproduced if ok else VerdictStatus.failed,
            paper_value=c.paper_value, measured_value=m, delta=round(m - c.paper_value, 6),
            evidence="workspace/results/metrics.json",
        ))
    return out


def no_usable_data(state: RunState) -> str | None:
    """Reason string if the spec needs data but nothing was downloaded, after one data retry."""
    if not state.spec or not state.spec.datasets or not state.datasets:
        return None
    if any(d.local_paths for d in state.datasets):
        return None
    if state.route_history.count(Route.data_finder) < 1:
        return None
    reasons = "; ".join(f"{d.name}: {d.status} ({d.verify_note})" for d in state.datasets)
    return f"no dataset could be obtained: {reasons}"


def _workspace_code(ws: Path) -> str:
    parts: list[str] = []
    for p in sorted(ws.rglob("*")):
        rel = p.relative_to(ws)
        if not p.is_file() or rel.parts[0] in (".venv", "data", "results") or p.suffix not in (".py", ".md", ".txt"):
            continue
        parts.append(f"--- {rel}\n{p.read_text(errors='replace')}")
    return "\n".join(parts)[:CODE_CHARS]


def run(state: RunState, llm: LLM, tracer: Tracer, root: Path | None = None) -> None:
    assert state.spec and state.exec_result
    verdicts = compare_claims(state.spec.claims, state.exec_result)
    state.verdicts = verdicts
    open_ = [v for v in verdicts if v.status == VerdictStatus.failed]
    if not open_:
        state.route, state.critic_feedback = Route.reporter, ""
        tracer.event("critic", route="reporter", statuses=[v.status.value for v in verdicts])
        return
    if state.exec_result.stderr_tail.startswith("[install]"):
        # nothing ran; only the Coder's requirements.txt can change this
        msg = ("Dependency install failed before main.py ran. Fix requirements.txt "
               f"(names, versions, CPU wheels):\n{state.exec_result.stderr_tail[-1500:]}")
        for v in open_:
            v.diagnosis = "not run: dependency install failed"
        state.route, state.critic_feedback = Route.coder, msg
        tracer.event("critic", route="coder", rule="install_failed")
        return
    if reason := no_usable_data(state):
        for v in open_:
            v.status, v.diagnosis = VerdictStatus.unverifiable, reason
        state.route, state.critic_feedback = Route.reporter, reason
        tracer.event("critic", route="reporter", rule="no_usable_data", explanation=reason)
        return
    ws = state.run_dir(root) / "workspace" if root else None
    prompt = (
        f"ATTEMPT: {state.attempt}  PRIOR ROUTES: {[r.value for r in state.route_history]}\n"
        f"CLAIMS:\n{[c.model_dump() for c in state.spec.claims]}\n"
        f"VERDICTS:\n{[v.model_dump() for v in verdicts]}\n"
        f"EXEC RESULT:\n{state.exec_result.model_dump_json()}\n"
        f"DATASETS:\n{[d.model_dump(include={'name', 'status', 'verify_note', 'local_paths', 'is_substitute'}) for d in state.datasets]}\n"
        f"SPEC (preprocessing / methods / evaluation):\n"
        f"{state.spec.model_dump_json(include={'preprocessing', 'models_or_methods', 'evaluation'})}\n"
        f"SPEC AMBIGUITIES: {state.spec.ambiguities}\n"
    )
    if ws and ws.exists():
        prompt += f"\nWORKSPACE CODE:\n{_workspace_code(ws)}\n"
    diag, usage = llm.structured(agent="critic", system=spec("critic"), prompt=prompt, schema=Diagnosis)
    state.tokens_used += usage.total
    route, rule = diag.route, None
    if route == Route.methods_extractor and Route.methods_extractor in state.route_history:
        # the paper was already re-read once; a second read has never changed the outcome
        route, rule = Route.reporter, "spec_reread_once"
    state.route, state.critic_feedback = route, diag.explanation
    for v in open_:
        v.diagnosis = diag.explanation
    tracer.event("critic", route=route.value, llm_route=diag.route.value, rule=rule,
                 explanation=diag.explanation, tokens=usage.total)
