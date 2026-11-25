"""Search real scholarly databases. Every Source comes from an API record, never from an LLM.

OpenAlex (free, no key) is the main index. Semantic Scholar is added when
SEMANTIC_SCHOLAR_API_KEY is set; without a key its shared pool is usually rate-limited,
so it is tried politely and skipped on 429. Only short keyword queries leave the machine.
"""
from __future__ import annotations

import os
import re
import threading
import time

import httpx

from paperrepro.state import Source

UA = {"User-Agent": "paperrepro/0.2 (citation finder)"}
OPENALEX = "https://api.openalex.org/works"
S2 = "https://api.semanticscholar.org/graph/v1/paper/search"
_s2_lock = threading.Lock()
_s2_last = [0.0]


def _abstract(inv: dict | None) -> str:
    """OpenAlex stores abstracts as {word: [positions]}; rebuild the text."""
    if not inv:
        return ""
    pos = sorted((i, w) for w, idx in inv.items() for i in idx)
    return " ".join(w for _, w in pos)


def _doi(raw: str | None) -> str:
    if not raw:
        return ""
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", raw.strip(), flags=re.I).lower()


def source_key(doi: str, title: str, fallback: str) -> str:
    if doi:
        return f"doi:{doi}"
    t = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
    return f"title:{t[:120]}" if t else fallback


def openalex(query: str, client: httpx.Client, n: int = 8) -> list[Source]:
    fields = "id,doi,display_name,publication_year,authorships,primary_location,abstract_inverted_index,cited_by_count"
    params = {"search": query, "per-page": n, "select": fields, "filter": "has_abstract:true"}
    r = client.get(OPENALEX, params=params, headers=UA)
    r.raise_for_status()
    out = []
    for w in r.json().get("results", []):
        title = (w.get("display_name") or "").strip()
        if not title:
            continue
        doi = _doi(w.get("doi"))
        loc = w.get("primary_location") or {}
        out.append(Source(
            id=source_key(doi, title, f"openalex:{w['id'].rsplit('/', 1)[-1]}"), title=title,
            authors=[a["author"]["display_name"] for a in w.get("authorships", []) if a.get("author")][:12],
            year=w.get("publication_year"), venue=((loc.get("source") or {}).get("display_name") or ""),
            doi=doi, url=f"https://doi.org/{doi}" if doi else (loc.get("landing_page_url") or w["id"]),
            abstract=_abstract(w.get("abstract_inverted_index")), cited_by=w.get("cited_by_count"),
            found_by=["openalex"]))
    return out


def semantic_scholar(query: str, client: httpx.Client, n: int = 8) -> list[Source]:
    key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
    headers = {**UA, **({"x-api-key": key} if key else {})}
    with _s2_lock:  # the public limit is about one request per second
        wait = 1.1 - (time.time() - _s2_last[0])
        if wait > 0:
            time.sleep(wait)
        _s2_last[0] = time.time()
        r = client.get(S2, params={"query": query, "limit": n,
                                   "fields": "title,authors,year,venue,externalIds,abstract,citationCount,url"},
                       headers=headers)
    if r.status_code == 429:
        return []  # shared pool busy; OpenAlex results stand on their own
    r.raise_for_status()
    out = []
    for p in r.json().get("data", []) or []:
        title = (p.get("title") or "").strip()
        if not title:
            continue
        doi = _doi((p.get("externalIds") or {}).get("DOI"))
        out.append(Source(
            id=source_key(doi, title, f"s2:{p.get('paperId', '')}"), title=title,
            authors=[a.get("name", "") for a in p.get("authors", [])][:12], year=p.get("year"),
            venue=p.get("venue") or "", doi=doi, url=f"https://doi.org/{doi}" if doi else (p.get("url") or ""),
            abstract=p.get("abstract") or "", cited_by=p.get("citationCount"), found_by=["semantic_scholar"]))
    return out


def merge(into: dict[str, Source], found: list[Source]) -> list[str]:
    """Add sources, merging duplicates (same DOI or title). Returns the ids, in order."""
    ids = []
    for s in found:
        cur = into.get(s.id)
        if cur is None:
            into[s.id] = s
        else:
            cur.found_by = sorted(set(cur.found_by) | set(s.found_by))
            if not cur.abstract and s.abstract:
                cur.abstract = s.abstract
        if s.id not in ids:
            ids.append(s.id)
    return ids


def search(queries: list[str], pool: dict[str, Source], client: httpx.Client,
           per_query: int = 6) -> list[str]:
    """Run each query against every available index; merge into pool; return candidate ids."""
    ids: list[str] = []
    use_s2 = bool(os.environ.get("SEMANTIC_SCHOLAR_API_KEY")) or os.environ.get("PAPERREPRO_S2", "") == "1"
    for q in queries[:3]:
        q = q.strip()[:200]
        if not q:
            continue
        for fn in (openalex, semantic_scholar) if use_s2 else (openalex,):
            try:
                found = fn(q, client, per_query)
            except (httpx.HTTPError, ValueError):
                continue  # one index failing must not sink the others
            for i in merge(pool, found):
                if i not in ids:
                    ids.append(i)
    return ids
