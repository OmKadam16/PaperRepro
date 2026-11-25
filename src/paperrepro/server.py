"""PaperRepro web app: `paperrepro serve` -> http://127.0.0.1:8765

Upload a draft, watch it being read and searched, then tick sources sentence by sentence;
citations and the reference list are written for you. One draft is processed at a time.

Safety: binds 127.0.0.1 only, checks Host and Origin, requires a custom header on every
write (blocks cross-site posts), validates ids, sizes and styles. Uploads go to OpenAI for
reading and judging; only short keyword queries go to the scholarly databases.
"""
from __future__ import annotations

import json
import queue
import re
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from typing import Callable
from urllib.parse import quote, unquote, urlparse

from paperrepro import cite
from paperrepro.state import Project
from paperrepro.tools.reader import MAX_BYTES

PID = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{6}$")
SID = re.compile(r"^p\d+s\d+$")
MAX_TEXT = 400_000
STYLES = ("numbered", "ieee", "apa")


class Desk:
    """Projects in memory (the source of truth while the server runs) plus a job worker."""

    def __init__(self, root: Path, process: Callable, find: Callable, can_run: str = ""):
        self.root, self.process, self.find, self.can_run = root, process, find, can_run
        self.projects: dict[str, Project] = {}
        self.locks: dict[str, threading.RLock] = {}
        self.busy: dict[str, str] = {}  # project id -> what the worker is doing for it
        self.q: queue.Queue = queue.Queue()
        self.guard = threading.Lock()
        root.mkdir(parents=True, exist_ok=True)
        for f in sorted(root.glob("*/project.json")):
            try:
                p = Project.load(f)
            except Exception:
                continue
            if p.status not in ("ready", "error"):  # the server stopped mid-way last time
                p.status = "error"
                p.error = "Interrupted: the server stopped while this draft was being processed. Upload it again."
            self.projects[p.id] = p
        threading.Thread(target=self._work, daemon=True).start()

    def lock(self, pid: str) -> threading.RLock:
        with self.guard:
            return self.locks.setdefault(pid, threading.RLock())

    def submit(self, filename: str, data: bytes) -> Project:
        p = Project(filename=filename[:200] or "draft.txt", progress="Waiting for the reader")
        with self.lock(p.id):
            p.save(self.root)
        self.projects[p.id] = p
        self.busy[p.id] = "process"
        self.q.put(("process", p.id, data))
        return p

    def find_more(self, pid: str, sid: str) -> None:
        self.busy[pid] = f"find:{sid}"
        self.q.put(("find", pid, sid))

    def _work(self) -> None:
        while True:
            kind, pid, arg = self.q.get()
            p = self.projects[pid]
            try:
                if kind == "process":
                    self.process(p, arg, self.root, self.lock(pid))
                else:
                    self.find(p, arg, self.root, self.lock(pid))
            except Exception as e:
                p.status, p.error = "error", f"{type(e).__name__}: {e}"
                traceback.print_exc()
            finally:
                self.busy.pop(pid, None)


def view(p: Project, busy: str | None) -> dict:
    """The project as the browser needs it, with citations already rendered by cite.py."""
    nums = cite.numbering(p)
    return {
        **json.loads(p.model_dump_json()),
        "busy": busy,
        "numbers": nums,
        "markers": {s.id: cite.marker(p, s.id, p.style, nums)
                    for pr in p.draft.paragraphs for s in pr.sentences if p.chosen.get(s.id)},
        "references": cite.references(p, p.style),
        "style_names": cite.STYLE_NAMES,
    }


def summary(p: Project, busy: str | None) -> dict:
    return {"id": p.id, "filename": p.filename, "title": p.draft.title, "created_at": p.created_at,
            "status": p.status, "progress": p.progress, "busy": bool(busy),
            "claims": len(p.claims), "with_sources": len({m.sentence_id for m in p.matches}),
            "cited": sum(1 for v in p.chosen.values() if v), "sources": len(cite.numbering(p))}


def make_handler(desk: Desk, port: int):
    template = files("paperrepro").joinpath("app_template.html").read_text()
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    class Handler(BaseHTTPRequestHandler):
        server_version = "PaperRepro"

        def log_message(self, fmt, *args):
            pass

        def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, data) -> None:
            self._send(code, json.dumps(data).encode(), "application/json")

        def _page(self, data: dict) -> None:
            blob = json.dumps(data).replace("</", "<\\/")
            self._send(200, template.replace("/*__APP_DATA__*/null", blob).encode(), "text/html; charset=utf-8")

        def _project(self, pid: str) -> Project | None:
            return desk.projects.get(pid) if PID.match(pid) else None

        def _list(self) -> list[dict]:
            ps = sorted(desk.projects.values(), key=lambda p: -p.created_at)
            return [summary(p, desk.busy.get(p.id)) for p in ps]

        # ---------------------------------------------------------------- GET
        def do_GET(self) -> None:
            if self.headers.get("Host", "") not in hosts:
                return self._json(403, {"error": "bad host"})
            path = urlparse(self.path).path.rstrip("/") or "/"
            if path == "/":
                return self._page({"page": "home", "drafts": self._list(), "can_run": desk.can_run})
            if path == "/api/drafts":
                return self._json(200, {"drafts": self._list()})
            m = re.fullmatch(r"/d/([^/]+)", path)
            if m and (p := self._project(m.group(1))):
                with desk.lock(p.id):
                    return self._page({"page": "editor", "project": view(p, desk.busy.get(p.id))})
            m = re.fullmatch(r"/api/d/([^/]+)", path)
            if m and (p := self._project(m.group(1))):
                with desk.lock(p.id):
                    return self._json(200, view(p, desk.busy.get(p.id)))
            m = re.fullmatch(r"/api/d/([^/]+)/export\.(txt|docx)", path)
            if m and (p := self._project(m.group(1))):
                with desk.lock(p.id):
                    stem = re.sub(r"[^\w\- ]+", "", Path(p.filename).stem)[:60].strip() or "draft"
                    name = f"{stem} (cited).{m.group(2)}"
                    disp = {"Content-Disposition":
                            f"attachment; filename=\"draft.{m.group(2)}\"; filename*=UTF-8''{quote(name)}"}
                    if m.group(2) == "txt":
                        return self._send(200, cite.to_text(p).encode(), "text/plain; charset=utf-8", disp)
                    return self._send(200, cite.to_docx(p),
                                      "application/vnd.openxmlformats-officedocument.wordprocessingml.document", disp)
            return self._json(404, {"error": "not found"})

        # ---------------------------------------------------------------- POST
        def do_POST(self) -> None:
            if self.headers.get("Host", "") not in hosts:
                return self._json(403, {"error": "bad host"})
            origin = self.headers.get("Origin")
            if origin and urlparse(origin).netloc not in hosts:
                return self._json(403, {"error": "cross-origin request refused"})
            if self.headers.get("X-PaperRepro") != "1":
                return self._json(403, {"error": "missing app header"})
            n = int(self.headers.get("Content-Length") or 0)
            if n <= 0:
                return self._json(400, {"error": "empty request"})
            if n > MAX_BYTES:
                return self._json(413, {"error": f"files up to {MAX_BYTES // (1024 * 1024)} MB, please"})
            path = urlparse(self.path).path
            body = self.rfile.read(n)

            if path == "/api/upload":
                if desk.can_run:
                    return self._json(409, {"error": desk.can_run})
                name = unquote(self.headers.get("X-Filename", "draft")).replace("/", "_").replace("\\", "_")
                if not re.search(r"\.(pdf|docx|txt|md|markdown|tex)$", name, re.I):
                    return self._json(400, {"error": "upload a PDF, a Word file (.docx), or plain text (.txt, .md)"})
                return self._json(201, {"id": desk.submit(name, body).id})

            if not self.headers.get("Content-Type", "").startswith("application/json"):
                return self._json(403, {"error": "JSON only"})
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                return self._json(400, {"error": "invalid JSON"})

            if path == "/api/paste":
                if desk.can_run:
                    return self._json(409, {"error": desk.can_run})
                text = str(data.get("text", "")).strip()
                if len(text) < 40:
                    return self._json(400, {"error": "paste at least a few sentences"})
                if len(text) > MAX_TEXT:
                    return self._json(400, {"error": "that is very long; upload it as a file instead"})
                title = re.sub(r"[^\w\- ]+", "", str(data.get("title", "")))[:60].strip() or "Pasted draft"
                return self._json(201, {"id": desk.submit(f"{title}.txt", text.encode()).id})

            m = re.fullmatch(r"/api/d/([^/]+)/(choose|style|find)", path)
            p = self._project(m.group(1)) if m else None
            if not p:
                return self._json(404, {"error": "not found"})
            action = m.group(2)
            with desk.lock(p.id):
                if action == "style":
                    if data.get("style") not in STYLES:
                        return self._json(400, {"error": "unknown style"})
                    p.style = data["style"]
                elif action == "choose":
                    sid, src, on = str(data.get("sentence_id", "")), str(data.get("source_id", "")), bool(data.get("on"))
                    allowed = {mt.source_id for mt in p.matches if mt.sentence_id == sid}
                    if not SID.match(sid) or src not in allowed:
                        return self._json(400, {"error": "that source was not found for this sentence"})
                    cur = [x for x in p.chosen.get(sid, []) if x != src]
                    p.chosen[sid] = cur + [src] if on else cur
                    if not p.chosen[sid]:
                        p.chosen.pop(sid)
                elif action == "find":
                    sid = str(data.get("sentence_id", ""))
                    if desk.can_run:
                        return self._json(409, {"error": desk.can_run})
                    if not SID.match(sid) or not p.draft.sentence(sid):
                        return self._json(400, {"error": "unknown sentence"})
                    if desk.busy.get(p.id):
                        return self._json(409, {"error": "still working on this draft; try again in a moment"})
                    desk.find_more(p.id, sid)
                p.save(desk.root)
                return self._json(200, view(p, desk.busy.get(p.id)))

    return Handler


def serve(root: Path, port: int = 8765) -> None:
    from paperrepro.env import load_dotenv
    from paperrepro.llm import LLMError, make_llm
    from paperrepro.pipeline import find_for_sentence, process

    load_dotenv()
    can_run, llm = "", None
    try:
        llm = make_llm()
    except LLMError as e:
        can_run = f"{e}. Add the key to .env and restart `paperrepro serve`."

    desk = Desk(root,
                process=lambda p, data, r, lock: process(p, data, llm, r, lock=lock),
                find=lambda p, sid, r, lock: find_for_sentence(p, sid, llm, r, lock=lock),
                can_run=can_run)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(desk, port))
    state = "ready" if not can_run else "NOT READY: " + can_run
    print(f"PaperRepro: http://127.0.0.1:{port}   [{state}]   Ctrl+C to stop", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
