from __future__ import annotations

from paperrepro.agents.base import spec
from paperrepro.llm import LLM
from paperrepro.state import Paper, RunState
from paperrepro.tools.fetch import fetch_paper
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
    paper.source_url = state.url
    paper.notes = "\n".join(filter(None, [*notes, paper.notes]))
    state.paper = paper
    state.tokens_used += usage.total
    tracer.event("ingestor", kind=doc.kind, resolved_url=doc.resolved_url, chars=len(doc.text),
                 sections=len(paper.sections), notes=notes, tokens=usage.total)
