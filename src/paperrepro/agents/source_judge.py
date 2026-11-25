from __future__ import annotations

import re

from paperrepro.agents.base import spec
from paperrepro.llm import LLM
from paperrepro.state import CitableClaim, JudgementList, Match, Source
from paperrepro.trace import Tracer

ABSTRACT_CHARS = 1500
MAX_PER_SENTENCE = 6


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", t).strip().lower()


def run(claim: CitableClaim, sentence: str, candidates: list[Source], llm: LLM,
        tracer: Tracer) -> tuple[list[Match], int]:
    """Judge candidates for one sentence. Code, not the model, enforces the honesty rules."""
    if not candidates:
        return [], 0
    by_id = {s.id: s for s in candidates}
    lines = []
    for s in candidates:
        abstract = s.abstract[:ABSTRACT_CHARS] if s.abstract else "(no abstract available)"
        lines.append(f"- id: {s.id}\n  title: {s.title}\n  year: {s.year or '?'}  venue: {s.venue or '?'}\n  abstract: {abstract}")
    prompt = f"SENTENCE: {sentence}\nCLAIM: {claim.claim}\n\nCANDIDATES:\n" + "\n".join(lines)
    out, usage = llm.structured(agent="source_judge", system=spec("source_judge"), prompt=prompt,
                                schema=JudgementList)
    matches, downgraded, dropped_quotes = [], 0, 0
    for j in out.judgements:
        src = by_id.get(j.source_id)
        if src is None or j.verdict == "unrelated":
            continue
        verdict, evidence = j.verdict, j.evidence.strip()
        if evidence and _norm(evidence) not in _norm(src.abstract):
            evidence, dropped_quotes = "", dropped_quotes + 1  # never show a quote that isn't there
        if verdict == "supports" and (not src.abstract or not evidence):
            verdict, downgraded = "related", downgraded + 1  # "supports" needs checkable text
        matches.append(Match(sentence_id=claim.sentence_id, source_id=src.id, verdict=verdict,
                             reason=j.reason.strip(), evidence=evidence))
    matches.sort(key=lambda m: (m.verdict != "supports", -(by_id[m.source_id].cited_by or 0)))
    matches = matches[:MAX_PER_SENTENCE]
    tracer.event("source_judge", sentence=claim.sentence_id, candidates=len(candidates),
                 supports=sum(m.verdict == "supports" for m in matches),
                 related=sum(m.verdict == "related" for m in matches),
                 downgraded=downgraded, dropped_quotes=dropped_quotes,
                 tokens=usage.total, model=usage.model)
    return matches, usage.total
