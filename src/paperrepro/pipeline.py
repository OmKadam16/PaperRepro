"""Draft -> citable sentences -> real candidate papers -> judged matches. Saves as it goes.

Steps: reading (with OCR for scanned pages) -> finding_claims -> searching + checking
(per sentence, a few in parallel) -> ready. Every LLM call is traced in trace.jsonl.
"""
from __future__ import annotations

import re
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from paperrepro.agents import claim_finder, ocr, source_judge
from paperrepro.llm import LLM
from paperrepro.state import CitableClaim, Project
from paperrepro.tools import literature
from paperrepro.tools.reader import looks_like_heading, read_upload
from paperrepro.tools.segment import build_draft
from paperrepro.trace import Tracer

WORKERS = 4
CANDIDATES = 10  # per sentence, sent to the judge


def _blocks_with_ocr(raw, llm: LLM, tracer: Tracer, project: Project) -> tuple[list[tuple[str, str]], int]:
    blocks, tokens = [], 0
    for kind, text in raw.blocks:
        m = re.fullmatch(r"__OCR_PAGE_(\d+)__", text) if kind == "ocr" else None
        if not m:
            blocks.append((kind, text))
            continue
        page = int(m.group(1))
        project.progress = f"Reading scanned page {page} with OCR"
        page_text, t = ocr.run(page, raw.scans[page], llm, tracer)
        tokens += t
        project.draft.ocr_pages.append(page)
        for chunk in re.split(r"\n\s*\n", page_text):
            chunk = re.sub(r"\s+", " ", chunk).strip()
            if chunk:
                blocks.append(("heading" if looks_like_heading(chunk) else "body", chunk))
    return blocks, tokens


def find_and_check(project: Project, claims: list[CitableClaim], llm: LLM, root: Path,
                   tracer: Tracer, client: httpx.Client, lock: threading.RLock | None = None) -> None:
    """Search and judge each claim; results are added to the project as each one finishes.
    `lock` is shared with the web server so a person's ticks never race the pipeline."""
    lock = lock or threading.RLock()
    done = [0]

    def one(claim: CitableClaim) -> None:
        sent = project.draft.sentence(claim.sentence_id)
        with lock:
            pool = dict(project.sources)
        ids = literature.search(claim.queries, pool, client)[:CANDIDATES]
        tracer.event("literature", sentence=claim.sentence_id, queries=claim.queries, candidates=len(ids))
        matches, tokens = source_judge.run(claim, sent.text if sent else claim.claim,
                                           [pool[i] for i in ids], llm, tracer)
        with lock:
            for m in matches:  # only sources that survived judging are kept
                project.sources.setdefault(m.source_id, pool[m.source_id])
            project.matches = [x for x in project.matches if x.sentence_id != claim.sentence_id] + matches
            project.tokens_used += tokens
            done[0] += 1
            project.progress = f"Checked {done[0]} of {len(claims)} sentences"
            project.save(root)

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        list(ex.map(one, claims))


def process(project: Project, data: bytes, llm: LLM, root: Path,
            client: httpx.Client | None = None, lock: threading.RLock | None = None) -> Project:
    lock = lock or threading.RLock()
    tracer = Tracer(project.dir(root) / "trace.jsonl")
    own = client is None
    client = client or httpx.Client(timeout=30, follow_redirects=True)
    try:
        project.status, project.progress = "reading", "Reading your draft"
        project.save(root)
        raw = read_upload(project.filename, data)
        blocks, tokens = _blocks_with_ocr(raw, llm, tracer, project)
        ocr_pages = list(project.draft.ocr_pages)
        project.draft = build_draft(blocks)
        project.draft.ocr_pages = ocr_pages
        project.tokens_used += tokens
        n = len(project.draft.all_sentences())
        tracer.event("reader", paragraphs=len(project.draft.paragraphs), sentences=n,
                     ocr_pages=project.draft.ocr_pages)

        project.status, project.progress = "finding_claims", f"Looking through {n} sentences for claims that need a source"
        project.save(root)
        claims, tokens = claim_finder.run(project.draft, llm, tracer)
        project.claims, project.tokens_used = claims, project.tokens_used + tokens

        project.status, project.progress = "searching", f"Searching the literature for {len(claims)} sentences"
        project.save(root)
        find_and_check(project, claims, llm, root, tracer, client, lock)
        project.status = "ready"
        cited = len({m.sentence_id for m in project.matches})
        project.progress = f"Found sources for {cited} of {len(claims)} sentences"
    except Exception as e:  # keep what we have; show the reason
        project.status, project.error = "error", f"{type(e).__name__}: {e}"
        tracer.event("pipeline", error=project.error)
    finally:
        if own:
            client.close()
    with lock:
        project.save(root)
    tracer.event("pipeline", status=project.status, tokens=project.tokens_used)
    return project


def find_for_sentence(project: Project, sentence_id: str, llm: LLM, root: Path,
                      client: httpx.Client | None = None, lock: threading.RLock | None = None) -> Project:
    """The person asked for sources for one sentence the claim finder skipped."""
    tracer = Tracer(project.dir(root) / "trace.jsonl")
    own = client is None
    client = client or httpx.Client(timeout=30, follow_redirects=True)
    try:
        claims, tokens = claim_finder.run(project.draft, llm, tracer, only={sentence_id}, force=True)
        project.tokens_used += tokens
        if claims:
            with lock or threading.RLock():
                project.claims = [c for c in project.claims if c.sentence_id != sentence_id] + claims
            find_and_check(project, claims, llm, root, tracer, client, lock)
        else:
            tracer.event("pipeline", sentence=sentence_id, note="no searchable claim in this sentence")
    finally:
        if own:
            client.close()
    with lock or threading.RLock():
        project.save(root)
    return project
