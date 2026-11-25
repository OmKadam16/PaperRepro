from __future__ import annotations

from paperrepro.agents.base import spec
from paperrepro.llm import LLM
from paperrepro.state import OcrPage
from paperrepro.trace import Tracer


def run(page: int, png: bytes, llm: LLM, tracer: Tracer) -> tuple[str, int]:
    """Transcribe one scanned page. Returns (text, tokens)."""
    out, usage = llm.structured(agent="ocr", system=spec("ocr"), prompt=f"Page {page}.",
                                schema=OcrPage, image_png=png)
    tracer.event("ocr", page=page, chars=len(out.text), tokens=usage.total, model=usage.model)
    return out.text, usage.total
