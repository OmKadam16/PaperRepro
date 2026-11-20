"""HTTP probing and size-capped downloads. Nothing here decides what to fetch."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

UA = {"User-Agent": "paperrepro/0.1 (research reproduction tool)"}


@dataclass
class Probe:
    status: int  # HTTP status, or 0 for a network error
    size_bytes: int | None
    final_url: str
    error: str = ""
    content_type: str = ""

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300


def _size(r: httpx.Response) -> int | None:
    cr = r.headers.get("content-range", "")  # "bytes 0-0/12345"
    if m := re.search(r"/(\d+)$", cr):
        return int(m.group(1))
    cl = r.headers.get("content-length")
    # a 206 without Content-Range only tells us the length of the 1-byte slice
    return int(cl) if cl and cl.isdigit() and r.status_code != 206 else None


def probe(url: str, client: httpx.Client) -> Probe:
    """HEAD the URL (following redirects); fall back to a 1-byte ranged GET if HEAD is refused."""
    try:
        r = client.head(url, follow_redirects=True, headers=UA)
        if r.status_code in (403, 405, 501):  # some servers refuse HEAD but allow GET
            with client.stream("GET", url, follow_redirects=True,
                               headers={**UA, "Range": "bytes=0-0"}) as g:
                if g.status_code in (200, 206):
                    return Probe(200, _size(g), str(g.url), content_type=g.headers.get("content-type", ""))
        return Probe(r.status_code, _size(r), str(r.url),
                     content_type=r.headers.get("content-type", ""))
    except httpx.HTTPError as e:
        return Probe(0, None, url, error=repr(e))


RETRY_SLEEP_S = 5.0


def get_with_retry(client: httpx.Client, url: str, retry_on: tuple[int, ...] = (429, 503),
                   tries: int = 3) -> httpx.Response:
    """GET with linear backoff on transient refusals (rate limits)."""
    for i in range(tries):
        r = client.get(url, follow_redirects=True, headers=UA)
        if r.status_code not in retry_on or i == tries - 1:
            return r
        time.sleep(RETRY_SLEEP_S * (i + 1))
    return r


class DownloadError(RuntimeError):
    pass


def download(url: str, dest: Path, client: httpx.Client, max_bytes: int) -> int:
    """Stream to dest, aborting if more than max_bytes arrive. Returns bytes written."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    n = 0
    try:
        with client.stream("GET", url, follow_redirects=True, headers=UA) as r:
            if r.status_code != 200:
                raise DownloadError(f"{url}: HTTP {r.status_code}")
            with tmp.open("wb") as f:
                for chunk in r.iter_bytes(1 << 20):
                    n += len(chunk)
                    if n > max_bytes:
                        raise DownloadError(f"{url}: exceeded size budget ({max_bytes} bytes)")
                    f.write(chunk)
    except httpx.HTTPError as e:
        tmp.unlink(missing_ok=True)
        raise DownloadError(f"{url}: network error {e!r}") from e
    except DownloadError:
        tmp.unlink(missing_ok=True)
        raise
    tmp.replace(dest)
    return n
