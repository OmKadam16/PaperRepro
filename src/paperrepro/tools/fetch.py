"""Fetch a paper's full text from arXiv, bioRxiv, or a plain URL.

bioRxiv's website sits behind Cloudflare and usually rejects scripted clients (HTTP 403/429),
so for bioRxiv we try, in order: the PDF, Europe PMC's JATS full text, then the bioRxiv API
abstract (marked as abstract-only). Every failure says what was tried.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import httpx

from paperrepro.tools.parse import ParseError, html_to_text, jats_to_text, pdf_to_text

UA = {"User-Agent": "paperrepro/0.1 (research reproduction tool)"}
EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"

ARXIV_RE = re.compile(
    r"(?:arxiv\.org/(?:abs|pdf|html)/|^arxiv:)(\d{4}\.\d{4,5}(?:v\d+)?|[a-z\-]+(?:\.[A-Z]{2})?/\d{7})",
    re.I,
)
BIORXIV_RE = re.compile(r"(?:biorxiv\.org/content/(?:early/[\d/]+/)?|^doi:|doi\.org/)?"
                        r"(10\.(?:1101|64898)/)?(\d{4}\.\d{2}\.\d{2}\.\d{6})(v\d+)?", re.I)


class FetchError(RuntimeError):
    pass


@dataclass
class Fetched:
    text: str
    kind: str  # pdf | jats | html | abstract
    resolved_url: str
    notes: list[str] = field(default_factory=list)


def arxiv_id(url: str) -> str | None:
    m = ARXIV_RE.search(url.strip())
    return m.group(1).removesuffix(".pdf") if m else None


def biorxiv_doi(url: str) -> str | None:
    if "biorxiv" not in url.lower() and not url.lower().startswith(("doi:", "10.")):
        return None
    m = BIORXIV_RE.search(url.strip())
    if not m:
        return None
    return f"{m.group(1) or '10.1101/'}{m.group(2)}"


def _get(client: httpx.Client, url: str, **kw) -> httpx.Response:
    try:
        return client.get(url, follow_redirects=True, headers=UA, **kw)
    except httpx.HTTPError as e:
        raise FetchError(f"network error fetching {url}: {e!r}") from e


def _is_pdf(r: httpx.Response) -> bool:
    return r.content[:4] == b"%PDF" or "pdf" in r.headers.get("content-type", "")


def fetch_arxiv(aid: str, client: httpx.Client) -> Fetched:
    url = f"https://arxiv.org/pdf/{aid}"
    r = _get(client, url)
    if r.status_code != 200 or not _is_pdf(r):
        raise FetchError(f"arXiv {aid}: expected a PDF from {url}, got HTTP {r.status_code} "
                         f"({r.headers.get('content-type', '?')})")
    try:
        return Fetched(pdf_to_text(r.content), "pdf", url)
    except ParseError as e:
        raise FetchError(f"arXiv {aid}: {e}") from e


def _epmc_fulltext(doi: str, client: httpx.Client) -> tuple[str, str] | None:
    r = _get(client, f"{EPMC}/search",
             params={"query": f'DOI:"{doi}"', "format": "json", "resultType": "lite"})
    if r.status_code != 200:
        return None
    hits = [h for h in r.json().get("resultList", {}).get("result", []) if h.get("source") == "PPR"]
    for h in hits:
        url = f"{EPMC}/{h['id']}/fullTextXML"
        x = _get(client, url)
        if x.status_code == 200 and x.content.lstrip().startswith(b"<"):
            try:
                return jats_to_text(x.content), url
            except ParseError:
                continue
    return None


def fetch_biorxiv(doi: str, client: httpx.Client) -> Fetched:
    tried: list[str] = []
    pdf_url = f"https://www.biorxiv.org/content/{doi}.full.pdf"
    r = _get(client, pdf_url)
    if r.status_code == 200 and _is_pdf(r):
        try:
            return Fetched(pdf_to_text(r.content), "pdf", pdf_url)
        except ParseError as e:
            tried.append(f"PDF unparseable ({e})")
    else:
        tried.append(f"bioRxiv PDF HTTP {r.status_code}")
    epmc = _epmc_fulltext(doi, client)
    if epmc:
        return Fetched(epmc[0], "jats", epmc[1], [f"full text via Europe PMC ({'; '.join(tried)})"])
    tried.append("no Europe PMC full text")
    api = f"https://api.biorxiv.org/details/biorxiv/{doi}"
    a = _get(client, api)
    coll = a.json().get("collection", []) if a.status_code == 200 else []
    if not coll:
        raise FetchError(f"bioRxiv {doi}: not found. Tried: {'; '.join(tried)}; API HTTP {a.status_code}")
    latest = coll[-1]
    text = f"TITLE: {latest.get('title', '')}\nAUTHORS: {latest.get('authors', '')}\n\n## Abstract\n{latest.get('abstract', '')}"
    return Fetched(text, "abstract", api,
                   [f"FULL TEXT UNAVAILABLE, abstract only ({'; '.join(tried)}). "
                    "Methods details are missing; claims will likely be unverifiable."])


def fetch_url(url: str, client: httpx.Client) -> Fetched:
    r = _get(client, url)
    if r.status_code != 200:
        raise FetchError(f"{url}: HTTP {r.status_code}")
    try:
        if _is_pdf(r):
            return Fetched(pdf_to_text(r.content), "pdf", str(r.url))
    except ParseError as e:
        raise FetchError(f"{url}: {e}") from e
    text = html_to_text(r.text)
    if len(text) < 500:
        raise FetchError(f"{url}: page has almost no text ({len(text)} chars); blocked or JS-only?")
    return Fetched(text, "html", str(r.url))


def fetch_paper(url: str, client: httpx.Client | None = None) -> Fetched:
    own = client is None
    client = client or httpx.Client(timeout=120)
    try:
        if aid := arxiv_id(url):
            return fetch_arxiv(aid, client)
        if doi := biorxiv_doi(url):
            return fetch_biorxiv(doi, client)
        return fetch_url(url, client)
    finally:
        if own:
            client.close()
