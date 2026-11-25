"""Stage 5: draft -> exact measures -> structured peer review."""
from __future__ import annotations

import threading
from pathlib import Path

from paperrepro.agents import reviewer
from paperrepro.llm import LLM
from paperrepro.measures import measure
from paperrepro.pipeline import _blocks_with_ocr
from paperrepro.state import Project, Review
from paperrepro.tools.reader import read_upload
from paperrepro.tools.segment import build_draft
from paperrepro.trace import Tracer


def run(rv: Review, data: bytes, llm: LLM, root: Path, lock: threading.RLock | None = None) -> Review:
    lock = lock or threading.RLock()
    tracer = Tracer(rv.path(root).parent / "trace.jsonl")

    def save(progress: str) -> None:
        with lock:
            rv.progress = progress
            rv.save(root)

    try:
        rv.status = "working"
        save("Reading your draft")
        raw = read_upload(rv.filename, data)
        scratch = Project(filename=rv.filename)  # OCR helper records pages on a Project
        blocks, t = _blocks_with_ocr(raw, llm, tracer, scratch)
        draft = build_draft(blocks)
        draft.ocr_pages = scratch.draft.ocr_pages
        with lock:
            rv.draft, rv.tokens_used = draft, rv.tokens_used + t
            rv.measures = measure(draft)
        if not draft.all_sentences():
            raise RuntimeError("no body text found to review")
        save(f"Reviewing {rv.measures.words:,} words")
        out, t = reviewer.run(draft, rv.measures, llm, tracer)
        with lock:
            rv.review, rv.tokens_used, rv.status = out, rv.tokens_used + t, "ready"
        save(f"Recommendation: {out.recommendation.replace('_', ' ')}")
    except Exception as e:
        with lock:
            rv.status, rv.error = "error", f"{type(e).__name__}: {e}"
        save("Stopped")
        tracer.event("reviewing", error=rv.error)
    return rv
