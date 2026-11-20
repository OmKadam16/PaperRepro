from __future__ import annotations

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
            evidence="results/metrics.json",
        ))
    return out


def run(state: RunState, llm: LLM, tracer: Tracer) -> None:
    assert state.spec and state.exec_result
    verdicts = compare_claims(state.spec.claims, state.exec_result)
    state.verdicts = verdicts
    open_ = [v for v in verdicts if v.status == VerdictStatus.failed]
    if not open_:
        state.route, state.critic_feedback = Route.reporter, ""
        tracer.event("critic", route="reporter", statuses=[v.status.value for v in verdicts])
        return
    prompt = (
        f"VERDICTS:\n{[v.model_dump() for v in verdicts]}\n"
        f"EXEC RESULT:\n{state.exec_result.model_dump_json()}\n"
        f"SPEC AMBIGUITIES: {state.spec.ambiguities}\n"
    )
    diag, usage = llm.structured(agent="critic", system=spec("critic"), prompt=prompt, schema=Diagnosis)
    state.route, state.critic_feedback = diag.route, diag.explanation
    state.tokens_used += usage.total
    for v in open_:
        v.diagnosis = diag.explanation
    tracer.event("critic", route=diag.route.value, explanation=diag.explanation, tokens=usage.total)
