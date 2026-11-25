from __future__ import annotations

import re
from pathlib import Path

import httpx

from paperrepro.agents.base import spec
from paperrepro.llm import LLM
from paperrepro.state import DatasetList, DatasetRef, RunState
from paperrepro.tools.data_sources import Unavailable, resolve
from paperrepro.tools.download import DownloadError, download
from paperrepro.trace import Tracer

MB = 1024 * 1024


def _slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_")[:60] or "dataset"


def verify_and_fetch(ref: DatasetRef, data_dir: Path, ws: Path, budget_left: int,
                     client: httpx.Client, download_files: bool = True) -> int:
    """Check ref against reality and download it. Mutates ref. Returns bytes used."""
    ref.verified, ref.verify_note, ref.local_paths = False, "", []  # code-owned fields
    if ref.status != "available":
        ref.verify_note = f"Data Finder marked it {ref.status}; not fetched"
        return 0
    try:
        files = resolve(ref, client)
    except Unavailable as u:
        ref.status, ref.verify_note = u.status, u.reason
        return 0
    known = [f.size_bytes for f in files if f.size_bytes is not None]
    total = sum(known)
    ref.size_mb = round(total / MB, 2) if known else None
    if total > budget_left:
        ref.status = "too_large"
        ref.verify_note = f"{total / MB:.0f} MB exceeds remaining data budget {budget_left / MB:.0f} MB"
        return 0
    ref.verified = True
    ref.verify_note = f"{len(files)} file(s) resolve" + ("" if len(known) == len(files)
                                                         else "; some sizes unreported")
    if not download_files:
        return 0
    used = 0
    dest_dir = data_dir / _slug(ref.name)
    for f in files:
        dest = dest_dir / _slug(f.name)
        try:
            used += download(f.url, dest, client, max_bytes=budget_left - used)
        except DownloadError as e:
            ref.status, ref.verified = "missing", False
            ref.verify_note = f"download failed: {e}"
            return used
        ref.local_paths.append(str(dest.relative_to(ws)))
    ref.size_mb = round(used / MB, 2)
    return used


def run(state: RunState, llm: LLM, tracer: Tracer, root: Path,
        client: httpx.Client | None = None) -> None:
    assert state.spec and state.paper, "extract first"
    prompt = (
        f"DATASETS MENTIONED: {state.spec.datasets}\n"
        f"DATA LINKS IN PAPER: {state.paper.data_links}\n"
        f"CODE LINKS IN PAPER: {state.paper.code_links}\n"
        f"SIZE BUDGET: {state.budget.max_data_mb} MB total\n"
    )
    if state.critic_feedback:
        prompt += f"\nCRITIC FEEDBACK:\n{state.critic_feedback}"
    result, usage = llm.structured(
        agent="data_finder", system=spec("data_finder"), prompt=prompt, schema=DatasetList
    )
    state.tokens_used += usage.total
    ws = state.run_dir(root) / "workspace"
    budget_left = state.budget.max_data_mb * MB
    own = client is None
    client = client or httpx.Client(timeout=120)
    try:
        for ref in result.items:
            budget_left -= verify_and_fetch(ref, ws / "data", ws, budget_left, client,
                                            download_files=not state.dry_run)
    finally:
        if own:
            client.close()
    state.datasets = result.items
    tracer.event("data_finder", tokens=usage.total, model=usage.model, datasets=[
        {"name": d.name, "source": d.source, "status": d.status, "verified": d.verified,
         "size_mb": d.size_mb, "note": d.verify_note, "local_paths": d.local_paths}
        for d in result.items])
