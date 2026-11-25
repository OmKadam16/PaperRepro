"""Local web app: `paperrepro serve` -> http://127.0.0.1:8765

People paste a paper link (or search arXiv by title), say what they want checked, and
watch the agents work live. Runs execute one at a time in a background worker.

Safety: this server runs LLM-written code on this machine and spends the configured API
key, so it binds to 127.0.0.1 only, checks Host/Origin (blocks DNS rebinding and other
sites posting to it), requires a custom header on writes (blocks cross-site form posts),
and validates every input. Do not expose it to a network until the sandbox is Docker.
"""
from __future__ import annotations

import json
import queue
import re
import threading
import time
import traceback
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlparse

import httpx

from paperrepro import site
from paperrepro.state import RunState

RUN_ID = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{6}$")
MAX_BODY = 10_000
MAX_REQUEST = 2_000
ARXIV_API = "https://export.arxiv.org/api/query"
ATOM = "{http://www.w3.org/2005/Atom}"


@dataclass
class Job:
    id: str
    url: str
    request: str
    status: str = "queued"  # queued | running | finished | failed
    created: float = field(default_factory=time.time)
    error: str = ""


class Lab:
    """Job queue + single worker. `runner(state)` runs the pipeline for one RunState."""

    def __init__(self, root: Path, runner: Callable[[RunState], None], dry_run: bool,
                 can_run: str = ""):
        self.root, self.runner, self.dry_run = root, runner, dry_run
        self.can_run = can_run  # empty = OK, else the reason runs cannot start
        self.jobs: dict[str, Job] = {}
        self.q: queue.Queue[str] = queue.Queue()
        self.lock = threading.Lock()
        threading.Thread(target=self._work, daemon=True).start()

    def submit(self, url: str, request: str) -> Job:
        state = RunState(url=url, user_request=request, dry_run=self.dry_run)
        state.save(self.root)  # visible in the lab immediately
        job = Job(id=state.run_id, url=url, request=request)
        with self.lock:
            self.jobs[job.id] = job
        self.q.put(job.id)
        return job

    def position(self, job_id: str) -> int:
        with self.lock:
            waiting = sorted((j for j in self.jobs.values() if j.status == "queued"), key=lambda j: j.created)
        return next((i for i, j in enumerate(waiting) if j.id == job_id), -1)

    def _work(self) -> None:
        while True:
            job_id = self.q.get()
            job = self.jobs[job_id]
            job.status = "running"
            try:
                state = RunState.load(self.root / job_id / "state.json")
                state.started_at = time.time()  # waiting in line is not run time
                self.runner(state)
                job.status = "finished"
            except Exception as e:  # the pipeline already records its own errors
                job.status, job.error = "failed", repr(e)
                traceback.print_exc()
            try:
                site.build_site(self.root)  # keep the static copy current too
            except Exception:
                traceback.print_exc()


# ---------------------------------------------------------------- arXiv search
def search_arxiv(q: str, client: httpx.Client | None = None) -> list[dict]:
    own = client is None
    client = client or httpx.Client(timeout=30)
    if m := re.fullmatch(r"(?:arxiv:)?\s*(\d{4}\.\d{4,5})(v\d+)?", q.strip(), re.I):
        params = {"id_list": m.group(1), "max_results": 1}  # a bare arXiv id: exact lookup
    else:
        # every word must match (arXiv ORs bare words, which buries the paper you meant)
        words = re.findall(r"[A-Za-z0-9]+", q)[:10]
        params = {"search_query": " AND ".join(f"all:{w}" for w in words), "max_results": 8}
    try:
        r = client.get(ARXIV_API, params=params, headers={"User-Agent": "paperrepro/0.1"},
                       follow_redirects=True)
        r.raise_for_status()
        root = ET.fromstring(r.content)
    finally:
        if own:
            client.close()
    out = []
    for e in root.findall(f"{ATOM}entry"):
        abs_url = (e.findtext(f"{ATOM}id") or "").strip()
        m = re.search(r"arxiv\.org/abs/([^v\s]+)", abs_url)
        if not m:
            continue
        out.append({
            "id": m.group(1), "url": f"https://arxiv.org/abs/{m.group(1)}",
            "title": re.sub(r"\s+", " ", e.findtext(f"{ATOM}title") or "").strip(),
            "authors": [a.findtext(f"{ATOM}name") or "" for a in e.findall(f"{ATOM}author")][:4],
            "year": (e.findtext(f"{ATOM}published") or "")[:4],
        })
    return out


# ---------------------------------------------------------------- HTTP
def make_handler(lab: Lab, port: int, search: Callable[[str], list[dict]] = search_arxiv):
    template = files("paperrepro").joinpath("site_template.html").read_text()
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    class Handler(BaseHTTPRequestHandler):
        server_version = "PaperRepro"

        def log_message(self, fmt, *args):  # quieter console
            pass

        # -- helpers
        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, data) -> None:
            self._send(code, json.dumps(data).encode(), "application/json")

        def _page(self, data: dict) -> None:
            data = {**data, "live": True, "nav": self._nav()}
            self._send(200, site._page(template, data).encode(), "text/html; charset=utf-8")

        def _nav(self) -> dict:
            briefs = self._briefs()
            return {"runs": [{"id": b["id"], "when": b["when"], "dry_run": b["dry_run"]} for b in briefs]}

        def _briefs(self) -> list[dict]:
            runs = []
            for d in site.list_runs(lab.root):
                try:
                    runs.append(self._overlay(site.load_run(d)))
                except Exception:
                    continue  # a run being written right now; next request will see it
            runs.sort(key=lambda r: r["started"])
            return [site._brief(r) for r in runs]

        def _overlay(self, r: dict) -> dict:
            job = lab.jobs.get(r["id"])
            if job and job.status in ("queued", "running"):
                r["status"] = job.status
                r["finished"] = False
            return r

        def _host_ok(self) -> bool:
            return self.headers.get("Host", "") in allowed_hosts

        # -- GET
        def do_GET(self) -> None:
            if not self._host_ok():
                return self._json(403, {"error": "bad host"})
            u = urlparse(self.path)
            path, qs = u.path.rstrip("/") or "/", parse_qs(u.query)
            try:
                if path in ("/", "/new"):
                    return self._page({"page": "new", "can_run": lab.can_run, "dry_run": lab.dry_run,
                                       "jobs": self._jobs()})
                if path == "/lab":
                    return self._page({"page": "lab", "runs": self._briefs()})
                if path == "/claims":
                    runs = [site.load_run(d) for d in site.list_runs(lab.root)]
                    claims = [{**v, "run": r["id"], "title": r["title"], "when": r["when"]}
                              for r in runs if not r["dry_run"] and r["finished"] for v in r["verdicts"]]
                    return self._page({"page": "claims", "claims": claims})
                if path == "/crew":
                    runs = [site.load_run(d) for d in site.list_runs(lab.root)]
                    return self._page({"page": "crew", "crew": site.crew(runs)})
                m = re.fullmatch(r"/run/([^/]+)", path)
                if m and RUN_ID.match(m.group(1)) and (lab.root / m.group(1) / "state.json").exists():
                    return self._page({"page": "run", **self._run_payload(m.group(1))})
                m = re.fullmatch(r"/api/run/([^/]+)", path)
                if m and RUN_ID.match(m.group(1)) and (lab.root / m.group(1) / "state.json").exists():
                    return self._json(200, self._run_payload(m.group(1)))
                m = re.fullmatch(r"/api/run/([^/]+)/report\.md", path)
                if m and RUN_ID.match(m.group(1)) and (lab.root / m.group(1) / "report.md").exists():
                    return self._send(200, (lab.root / m.group(1) / "report.md").read_bytes(),
                                      "text/markdown; charset=utf-8")
                if path == "/api/jobs":
                    return self._json(200, {"jobs": self._jobs()})
                if path == "/api/search":
                    q = (qs.get("q") or [""])[0].strip()[:200]
                    if len(q) < 3:
                        return self._json(400, {"error": "type at least 3 characters"})
                    try:
                        return self._json(200, {"results": search(q)})
                    except Exception as e:
                        return self._json(502, {"error": f"arXiv search failed: {type(e).__name__}"})
            except json.JSONDecodeError:
                return self._json(503, {"error": "run is being written; retry"})
            return self._json(404, {"error": "not found"})

        def _run_payload(self, run_id: str) -> dict:
            r = self._overlay(site.load_run(lab.root / run_id))
            ids = [x["id"] for x in self._briefs()]
            i = ids.index(run_id) if run_id in ids else -1
            job = lab.jobs.get(run_id)
            return {"run": r, "job": asdict(job) if job else None,
                    "position": lab.position(run_id) if job else -1,
                    "prev": ids[i - 1] if i > 0 else None,
                    "next": ids[i + 1] if 0 <= i < len(ids) - 1 else None}

        def _jobs(self) -> list[dict]:
            with lab.lock:
                jobs = sorted(lab.jobs.values(), key=lambda j: -j.created)
            return [asdict(j) for j in jobs[:20]]

        # -- POST
        def do_POST(self) -> None:
            if not self._host_ok():
                return self._json(403, {"error": "bad host"})
            origin = self.headers.get("Origin")
            if origin and urlparse(origin).netloc not in allowed_hosts:
                return self._json(403, {"error": "cross-origin request refused"})
            if self.headers.get("X-PaperRepro") != "1" or \
                    not self.headers.get("Content-Type", "").startswith("application/json"):
                return self._json(403, {"error": "missing app header"})
            if urlparse(self.path).path != "/api/runs":
                return self._json(404, {"error": "not found"})
            n = int(self.headers.get("Content-Length") or 0)
            if n <= 0 or n > MAX_BODY:
                return self._json(413, {"error": "request too large"})
            try:
                body = json.loads(self.rfile.read(n))
            except json.JSONDecodeError:
                return self._json(400, {"error": "invalid JSON"})
            url = str(body.get("url", "")).strip()
            request = str(body.get("request", "")).strip()
            if lab.can_run:
                return self._json(409, {"error": lab.can_run})
            p = urlparse(url)
            if p.scheme not in ("http", "https") or not p.netloc or len(url) > 500:
                return self._json(400, {"error": "give a full paper link starting with https://"})
            if len(request) > MAX_REQUEST:
                return self._json(400, {"error": f"keep the request under {MAX_REQUEST} characters"})
            job = lab.submit(url, request)
            return self._json(201, {"id": job.id})

    return Handler


def serve(root: Path, port: int = 8765, dry_run: bool = False) -> None:
    from paperrepro.orchestrator import run_pipeline

    root.mkdir(parents=True, exist_ok=True)
    can_run = ""
    if dry_run:
        from paperrepro.dryrun import DryRunLLM

        def runner(state: RunState) -> None:
            run_pipeline(state, DryRunLLM(), root)
    else:
        from paperrepro.env import load_dotenv
        from paperrepro.llm import LLMError, make_llm

        load_dotenv()
        try:
            llm = make_llm()
        except LLMError as e:
            llm, can_run = None, f"{e}. Add the key to .env and restart `paperrepro serve`."

        def runner(state: RunState) -> None:
            run_pipeline(state, llm, root)

    lab = Lab(root, runner, dry_run=dry_run, can_run=can_run)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(lab, port))
    mode = "DRY RUN (synthetic agents)" if dry_run else ("NOT READY: " + can_run if can_run else "live")
    print(f"PaperRepro web app: http://127.0.0.1:{port}   [{mode}]   Ctrl+C to stop")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
