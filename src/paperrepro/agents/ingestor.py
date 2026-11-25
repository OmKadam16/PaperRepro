from __future__ import annotations

from paperrepro.agents.base import spec
from paperrepro.llm import LLM
from paperrepro.state import Paper, RunState
from paperrepro.tools.fetch import fetch_paper
from paperrepro.tools.sections import slice_sections, unverified_numbers
from paperrepro.trace import Tracer

MAX_CHARS = 120_000


def run(state: RunState, llm: LLM, tracer: Tracer) -> None:
    doc = fetch_paper(state.url)  # raises FetchError with what was tried
    raw = doc.text[:MAX_CHARS]
    notes = list(doc.notes)
    if len(doc.text) > MAX_CHARS:
        notes.append(f"text truncated from {len(doc.text)} to {MAX_CHARS} chars")
    paper, usage = llm.structured(
        agent="ingestor", system=spec("ingestor"),
        prompt=f"Source URL: {state.url}\nFetched as: {doc.kind}\n\nRAW TEXT:\n{raw}", schema=Paper,
    )
    # Section text comes from the raw document, never from the LLM.
    paper.sections, missing = slice_sections(raw, [s.heading for s in paper.sections])
    if missing:
        notes.append(f"headings not found in raw text (merged into the previous section): {missing}")
    if bad := unverified_numbers(paper.tables, raw):
        notes.append(f"table numbers not found verbatim in the paper text, check: {bad}")
    paper.source_url = state.url
    paper.notes = "\n".join(filter(None, [*notes, paper.notes]))
    state.paper = paper
    state.tokens_used += usage.total
    kept = sum(len(s.text) for s in paper.sections)
    tracer.event("ingestor", kind=doc.kind, resolved_url=doc.resolved_url, chars=len(raw),
                 chars_kept=kept, sections=len(paper.sections), notes=notes, tokens=usage.total, model=usage.model)
