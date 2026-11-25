from __future__ import annotations

from paperrepro.agents.base import spec
from paperrepro.llm import LLM
from paperrepro.state import Draft, Measures, PeerReview
from paperrepro.trace import Tracer

MAX_CHARS = 60_000
CRITERIA = ["originality", "clarity", "methods", "evidence", "structure", "significance"]


def run(draft: Draft, measures: Measures, llm: LLM, tracer: Tracer) -> tuple[PeerReview, int]:
    lines, size = [], 0
    for p in draft.paragraphs:
        if p.kind == "references":
            continue
        block = f"## {p.sentences[0].text}" if p.kind == "heading" else "\n".join(f"[{s.id}] {s.text}" for s in p.sentences)
        if size + len(block) > MAX_CHARS:
            lines.append("(the rest of the draft was cut for length)")
            break
        lines.append(block)
        size += len(block)
    facts = (f"words: {measures.words}; sentences: {measures.sentences}; average sentence length: "
             f"{measures.avg_sentence_words} words; sentences over 40 words: {measures.long_sentences}; "
             f"sections found: {', '.join(measures.sections_found) or 'none'}; sections missing: "
             f"{', '.join(measures.sections_missing) or 'none'}; reference list: {'yes' if measures.has_references else 'no'}; "
             f"citation markers in text: {measures.citation_markers}")
    out, usage = llm.structured(agent="reviewer", system=spec("reviewer"),
                                prompt=f"MEASURED FACTS: {facts}\n\nDRAFT:\n\n" + "\n\n".join(lines), schema=PeerReview)
    valid = {s.id for s in draft.all_sentences()}
    for i in out.issues:
        i.sentence_ids = [s for s in i.sentence_ids if s in valid]
    seen, scores = set(), []
    for s in out.scores:  # exactly one per criterion, in a fixed order
        if s.criterion not in seen:
            seen.add(s.criterion)
            scores.append(s)
    out.scores = sorted(scores, key=lambda s: CRITERIA.index(s.criterion))
    out.issues.sort(key=lambda i: i.severity != "major")
    tracer.event("reviewer", scores={s.criterion: s.score for s in out.scores}, issues=len(out.issues),
                 recommendation=out.recommendation, tokens=usage.total, model=usage.model)
    return out, usage.total
