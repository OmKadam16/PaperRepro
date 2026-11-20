"""Turn a DatasetRef into concrete remote files, using each repository's canonical layout.

URLs are derived only from the accession / URL the paper (via the Data Finder) gave us,
following each repository's documented scheme. Anything that does not resolve raises
Unavailable; nothing is guessed beyond that.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import unquote, urlparse

import httpx

from paperrepro.state import DatasetRef
from paperrepro.tools.download import UA, get_with_retry, probe

MAX_FILES = 50


@dataclass
class RemoteFile:
    url: str
    name: str
    size_bytes: int | None = None


class Unavailable(Exception):
    def __init__(self, status: str, reason: str):
        super().__init__(reason)
        self.status, self.reason = status, reason  # status: "restricted" | "missing"


def _status_error(what: str, code: int, err: str = "", public: bool = False) -> Unavailable:
    """public=True: the repository has no access control, so a 403 is a refusal, not a restriction."""
    if code in (401, 403) and not public:
        return Unavailable("restricted", f"{what}: HTTP {code} (login or data-use agreement required)")
    return Unavailable("missing", f"{what}: {'network error ' + err if code == 0 else f'HTTP {code}'}")


def _name_from_url(url: str) -> str:
    return unquote(urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]) or "download"


# ---- GEO -------------------------------------------------------------------
def geo_series_dir(acc: str) -> str:
    num = acc[3:]
    stub = f"GSE{num[:-3]}nnn" if len(num) > 3 else "GSEnnn"
    return f"https://ftp.ncbi.nlm.nih.gov/geo/series/{stub}/{acc}/"


def resolve_geo(ref: DatasetRef, client: httpx.Client) -> list[RemoteFile]:
    m = re.search(r"GSE\d+", f"{ref.accession} {ref.url}", re.I)
    if not m:
        raise Unavailable("missing", "GEO: no GSE accession given")
    acc = m.group(0).upper()
    files: list[RemoteFile] = []
    for sub in ("matrix/", "suppl/"):
        url = geo_series_dir(acc) + sub
        # GEO is always public: a 403/429 from NCBI is rate limiting, not restricted data
        r = get_with_retry(client, url, retry_on=(403, 429, 503))
        if r.status_code == 404:
            continue
        if r.status_code != 200:
            raise Unavailable("missing", f"GEO {acc} {sub}: NCBI refused with HTTP {r.status_code} "
                                         "after retries (public data; likely rate-limited, retry later)")
        for href in re.findall(r'href="([^"/?#][^"?#]*)"', r.text):
            if not href.startswith("http") and href != "filelist.txt":
                files.append(RemoteFile(url + href, href))
    if not files:
        raise Unavailable("missing", f"GEO {acc}: no series matrix or supplementary files")
    return files


# ---- PhysioNet -------------------------------------------------------------
def resolve_physionet(ref: DatasetRef, client: httpx.Client) -> list[RemoteFile]:
    m = re.search(r"physionet\.org/(?:content|files)/([\w-]+)/([\d.]+)", ref.url) or \
        re.fullmatch(r"([\w-]+)/([\d.]+)", ref.accession.strip())
    if not m:
        raise Unavailable("missing", "PhysioNet: need a project URL or 'slug/version' accession")
    slug, ver = m.group(1), m.group(2)
    url = f"https://physionet.org/content/{slug}/get-zip/{ver}/"
    p = probe(url, client)
    if not p.ok:
        raise _status_error(f"PhysioNet {slug}/{ver}", p.status, p.error)
    return [RemoteFile(p.final_url, f"{slug}-{ver}.zip", p.size_bytes)]


# ---- Zenodo ----------------------------------------------------------------
def resolve_zenodo(ref: DatasetRef, client: httpx.Client) -> list[RemoteFile]:
    m = re.search(r"zenodo\.org/records?/(\d+)|zenodo\.(\d+)", f"{ref.url} {ref.accession}")
    if not m:
        raise Unavailable("missing", "Zenodo: no record id or 10.5281/zenodo.N DOI given")
    rid = m.group(1) or m.group(2)
    r = client.get(f"https://zenodo.org/api/records/{rid}", follow_redirects=True, headers=UA)
    if r.status_code != 200:
        raise _status_error(f"Zenodo {rid}", r.status_code)
    rec = r.json()
    if rec.get("metadata", {}).get("access_right", "open") != "open":
        raise Unavailable("restricted", f"Zenodo {rid}: access_right={rec['metadata']['access_right']}")
    files = [RemoteFile(f["links"]["self"], f["key"], f.get("size")) for f in rec.get("files", [])]
    if not files:
        raise Unavailable("missing", f"Zenodo {rid}: record has no files")
    return files


# ---- plain URL (also github raw, huggingface resolve URLs) -----------------
def resolve_url(ref: DatasetRef, client: httpx.Client) -> list[RemoteFile]:
    if not ref.url:
        raise Unavailable("missing", "no URL given")
    p = probe(ref.url, client)
    if not p.ok:
        raise _status_error(ref.url, p.status, p.error)
    if "text/html" in p.content_type:
        raise Unavailable("missing", f"{ref.url} is a web page, not a data file; need a direct file URL")
    return [RemoteFile(p.final_url, _name_from_url(ref.url), p.size_bytes)]


RESOLVERS = {"geo": resolve_geo, "physionet": resolve_physionet, "zenodo": resolve_zenodo}


def resolve(ref: DatasetRef, client: httpx.Client) -> list[RemoteFile]:
    """Remote files for ref, each with a probed size where the server reports one."""
    try:
        files = RESOLVERS.get(ref.source, resolve_url)(ref, client)
    except httpx.HTTPError as e:
        raise Unavailable("missing", f"{ref.source}: network error {e!r}") from e
    if len(files) > MAX_FILES:
        raise Unavailable("missing", f"{len(files)} files; more than {MAX_FILES}, refine the URL")
    for f in files:
        if f.size_bytes is None:
            p = probe(f.url, client)
            if not p.ok:
                raise _status_error(f.url, p.status, p.error, public=ref.source == "geo")
            f.size_bytes = p.size_bytes
    return files
