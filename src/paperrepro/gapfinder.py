"""Stage 1: idea -> framing -> real literature -> themes and gaps -> novelty check per gap.

Every paper comes from OpenAlex; the helpers only refer to papers they were shown, and
code drops gaps that point at nothing. Saves after each step so the page shows progress.
"""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from paperrepro.agents import gap_analyst, idea_framer, novelty_checker
from paperrepro.llm import LLM
from paperrepro.state import GapStudy, Source
from paperrepro.tools import literature
from paperrepro.trace import Tracer

MAX_PAPERS = 45  # what the analyst reads: enough to map a field, small enough to read well
PER_QUERY = 12
NOVELTY_PAPERS = 8


def _rank(pool: dict[str, Source], ids: list[str]) -> list[Source]:
    """Papers with abstracts first, then by how many queries found them, then citations."""
    hits: dict[str, int] = {}
    for i in ids:
        hits[i] = hits.get(i, 0) + 1
    uniq = list(dict.fromkeys(ids))
    uniq.sort(key=lambda i: (not pool[i].abstract, -hits[i], -(pool[i].cited_by or 0)))
    return [pool[i] for i in uniq[:MAX_PAPERS]]


def run(study: GapStudy, llm: LLM, root: Path, client: httpx.Client | None = None,
        lock: threading.RLock | None = None) -> GapStudy:
    lock = lock or threading.RLock()
    tracer = Tracer(study.path(root).parent / "trace.jsonl")
    own = client is None
    client = client or httpx.Client(timeout=30, follow_redirects=True)

    def save(progress: str) -> None:
        with lock:
            study.progress = progress
            study.save(root)

    try:
        study.status = "working"
        save("Framing your idea as research questions")
        study.framing, t = idea_framer.run(study.idea, llm, tracer)
        study.tokens_used += t

        save(f"Searching the literature with {len(study.framing.queries)} queries")
        pool: dict[str, Source] = {}
        found: list[str] = []
        for q in study.framing.queries:
            try:
                got = literature.openalex(q, client, PER_QUERY)
            except (httpx.HTTPError, ValueError):
                continue
            found += literature.merge(pool, got)
        papers = _rank(pool, found)
        tracer.event("literature", queries=study.framing.queries, unique=len(pool), kept=len(papers))
        with lock:
            study.papers = {p.id: p for p in papers}
        if not papers:
            raise RuntimeError("the literature search returned nothing; try describing the idea with more standard terms")

        save(f"Reading {len(papers)} papers and mapping the field")
        themes, gaps, t = gap_analyst.run(study.framing, study.idea, papers, llm, tracer)
        with lock:
            study.themes, study.gaps, study.tokens_used = themes, gaps, study.tokens_used + t
        save(f"Checking whether {len(gaps)} gaps are still open")

        done = [0]

        def check(i: int) -> None:
            g = study.gaps[i]
            q = " ".join(g.question.split()[:12])
            try:
                fresh = literature.openalex(q, client, NOVELTY_PAPERS)
            except (httpx.HTTPError, ValueError):
                fresh = []
            with lock:
                ids = literature.merge(study.papers, fresh)
                cands = [study.papers[x] for x in ids]
            checked, t = novelty_checker.run(g, cands, llm, tracer)
            with lock:
                study.gaps[i] = checked
                study.tokens_used += t
                done[0] += 1
            save(f"Checked {done[0]} of {len(study.gaps)} gaps")

        with ThreadPoolExecutor(max_workers=3) as ex:
            list(ex.map(check, range(len(study.gaps))))
        order = {"open": 0, "partly_addressed": 1, "unchecked": 2, "addressed": 3}
        with lock:
            study.gaps.sort(key=lambda g: order[g.novelty])
            study.status = "ready"
        save(f"{sum(g.novelty == 'open' for g in study.gaps)} open gaps from {len(papers)} papers")
    except Exception as e:
        with lock:
            study.status, study.error = "error", f"{type(e).__name__}: {e}"
        save("Stopped")
        tracer.event("gapfinder", error=study.error)
    finally:
        if own:
            client.close()
    return study
