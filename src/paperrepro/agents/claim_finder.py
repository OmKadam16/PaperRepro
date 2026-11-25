from __future__ import annotations

from paperrepro.agents.base import spec
from paperrepro.llm import LLM
from paperrepro.state import CitableClaim, ClaimList, Draft
from paperrepro.trace import Tracer

CHUNK_CHARS = 24_000  # keep each call well inside the model's comfort zone


def _chunks(draft: Draft, only: set[str] | None) -> list[str]:
    chunks, cur = [], []
    size = 0
    for p in draft.paragraphs:
        if p.kind == "references":
            continue
        if p.kind == "heading":
            lines = [f"## {p.sentences[0].text}"]
        else:
            lines = [f"[{s.id}] {s.text}" for s in p.sentences if only is None or s.id in only]
        if not lines:
            continue
        block = "\n".join(lines)
        if size + len(block) > CHUNK_CHARS and cur:
            chunks.append("\n\n".join(cur))
            cur, size = [], 0
        cur.append(block)
        size += len(block)
    if cur:
        chunks.append("\n\n".join(cur))
    return chunks


def run(draft: Draft, llm: LLM, tracer: Tracer, only: set[str] | None = None,
        force: bool = False) -> tuple[list[CitableClaim], int]:
    """Find citable sentences. `only` limits to some sentence ids; `force` means the person
    picked them, so every one gets search queries even if the helper would skip it."""
    valid = {s.id for s in draft.all_sentences()}
    claims: dict[str, CitableClaim] = {}
    tokens = 0
    note = ("\n\nThe author asked for sources for every sentence below. Return all of them."
            if force else "")
    for i, chunk in enumerate(_chunks(draft, only)):
        out, usage = llm.structured(agent="claim_finder", system=spec("claim_finder"),
                                    prompt=f"DRAFT (part {i + 1}):\n\n{chunk}{note}", schema=ClaimList)
        tokens += usage.total
        kept = 0
        for c in out.claims:
            if c.sentence_id in valid and c.sentence_id not in claims and c.queries:
                c.queries = [q.strip() for q in c.queries if q.strip()][:3]
                claims[c.sentence_id] = c
                kept += 1
        tracer.event("claim_finder", part=i + 1, proposed=len(out.claims), kept=kept,
                     tokens=usage.total, model=usage.model)
    order = {s.id: n for n, s in enumerate(draft.all_sentences())}
    return sorted(claims.values(), key=lambda c: order[c.sentence_id]), tokens
