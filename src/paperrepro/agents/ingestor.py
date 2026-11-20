from __future__ import annotations

import re

import httpx

from paperrepro.agents.base import spec
from paperrepro.llm import LLM
from paperrepro.state import Paper, RunState
from paperrepro.trace import Tracer

MAX_CHARS = 120_000


def normalize_url(url: str) -> str:
    m = re.match(r"https?://arxiv\.org/abs/(.+)", url)
    return f"https://arxiv.org/pdf/{m.group(1)}" if m else url


def fetch_text(url: str) -> str:
    r = httpx.get(normalize_url(url), follow_redirects=True, timeout=60,
                  headers={"User-Agent": "paperrepro/0.1"})
    r.raise_for_status()
    if "pdf" in r.headers.get("content-type", "") or r.content[:4] == b"%PDF":
        try:
            import fitz  # pymupdf
        except ImportError as e:
            raise RuntimeError("PDF parsing needs: pip install 'paperrepro[pdf]'") from e
        doc = fitz.open(stream=r.content, filetype="pdf")
        return "\n".join(page.get_text() for page in doc)
    return re.sub(r"<[^>]+>", " ", r.text)


def run(state: RunState, llm: LLM, tracer: Tracer) -> None:
    raw = fetch_text(state.url)[:MAX_CHARS]
    paper, usage = llm.structured(
        agent="ingestor", system=spec("ingestor"),
        prompt=f"Source URL: {state.url}\n\nRAW TEXT:\n{raw}", schema=Paper,
    )
    paper.source_url = state.url
    state.paper = paper
    state.tokens_used += usage.total
    tracer.event("ingestor", sections=len(paper.sections), tokens=usage.total)
