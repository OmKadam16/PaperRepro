"""PaperRepro web app: `paperrepro serve` -> http://127.0.0.1:8765

Pages follow the research process: dashboard, 1 gap, 2 plan, 3 figures, 4 cite, 5 review.
AI jobs run one at a time in a background worker; pages poll for progress.

Safety: binds 127.0.0.1 only, checks Host and Origin, requires a custom header on every
write (blocks cross-site posts), validates ids, sizes, types; static files are a fixed set.
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
from urllib.parse import parse_qs, quote, unquote, urlparse

from pydantic import ValidationError

from paperrepro import cite, figures, templates
from paperrepro.state import Figure, FigureSpec, GapStudy, Project, Record, Review
from paperrepro.tools.reader import MAX_BYTES

ID = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{6}$")
SID = re.compile(r"^p\d+s\d+$")
MAX_TEXT = 400_000
STYLES = ("numbered", "ieee", "apa")
STATIC = {"app.css": "text/css", "core.js": "text/javascript", "dashboard.js": "text/javascript",
          "gap.js": "text/javascript", "plan.js": "text/javascript", "figures.js": "text/javascript",
          "cite.js": "text/javascript", "review.js": "text/javascript"}
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
DOC_EXT = re.compile(r"\.(pdf|docx|txt|md|markdown|tex)$", re.I)


class Desk:
    """All records in memory (the source of truth while running) plus one AI job worker."""

    def __init__(self, root: Path, jobs: dict[str, Callable], can_run: str = ""):
        self.root, self.jobs, self.can_run = root, jobs, can_run
        self.projects: dict[str, Project] = {}
        self.gaps: dict[str, GapStudy] = {}
        self.reviews: dict[str, Review] = {}
        self.figures: dict[str, Figure] = {}
        self.locks: dict[str, threading.RLock] = {}
        self.busy: dict[str, str] = {}
        self.q: queue.Queue = queue.Queue()
        self.guard = threading.Lock()
        root.mkdir(parents=True, exist_ok=True)
        self._load()
        threading.Thread(target=self._work, daemon=True).start()

    def _load(self) -> None:
        stopped = "Interrupted: the server stopped while this was running. Start it again."
        for f in sorted(self.root.glob("*/project.json")):
            try:
                p = Project.load(f)
            except Exception:
                continue
            if p.status not in ("ready", "error"):
                p.status, p.error = "error", stopped
            self.projects[p.id] = p
        for cls, store in ((GapStudy, self.gaps), (Review, self.reviews), (Figure, self.figures)):
            for f in sorted((self.root / cls.KIND).glob(f"*/{cls.KIND}.json")):
                try:
                    r = cls.model_validate_json(f.read_text())
                except Exception:
                    continue
                if r.status in ("queued", "working"):
                    r.status, r.error = "error", stopped
                store[r.id] = r

    def lock(self, rid: str) -> threading.RLock:
        with self.guard:
            return self.locks.setdefault(rid, threading.RLock())

    def enqueue(self, kind: str, rid: str, arg=None) -> None:
        self.busy[rid] = kind if kind != "find" else f"find:{arg}"
        self.q.put((kind, rid, arg))

    def _work(self) -> None:
        while True:
            kind, rid, arg = self.q.get()
            rec = {"process": self.projects, "find": self.projects, "gap": self.gaps, "review": self.reviews}[kind][rid]
            try:
                self.jobs[kind](rec, arg, self.root, self.lock(rid))
            except Exception as e:
                rec.status, rec.error = "error", f"{type(e).__name__}: {e}"
                traceback.print_exc()
            finally:
                self.busy.pop(rid, None)

    # ---------------------------------------------------------------- summaries
    def counts(self) -> dict:
        return {"gap": len(self.gaps), "figures": len(self.figures), "cite": len(self.projects),
                "review": len(self.reviews), "plan_visited": (self.root / ".plan_visited").exists()}

    def recent(self, n: int = 8) -> list[dict]:
        items = []
        for g in self.gaps.values():
            items.append({"kind": "gap", "kind_label": "gap study", "title": g.idea[:90], "href": f"/gap/{g.id}",
                          "sub": g.progress or g.status, "status": g.status, "created_at": g.created_at})
        for p in self.projects.values():
            items.append({"kind": "draft", "kind_label": "draft", "title": p.draft.title or p.filename, "href": f"/d/{p.id}",
                          "sub": f"{sum(1 for v in p.chosen.values() if v)} cited" if p.status == "ready" else p.progress,
                          "status": p.status, "created_at": p.created_at})
        for r in self.reviews.values():
            items.append({"kind": "review", "kind_label": "review", "title": r.draft.title or r.filename, "href": f"/review/{r.id}",
                          "sub": r.progress or r.status, "status": r.status, "created_at": r.created_at})
        for f in self.figures.values():
            items.append({"kind": "figure", "kind_label": "figure", "title": f.title, "href": f"/figures/{f.id}",
                          "sub": f.spec.chart + " chart", "status": f.status, "created_at": f.created_at})
        return sorted(items, key=lambda x: -x["created_at"])[:n]

    def totals(self) -> dict:
        recs: list = [*self.projects.values(), *self.gaps.values(), *self.reviews.values(), *self.figures.values()]
        return {"papers": sum(len(g.papers) for g in self.gaps.values()), "gaps": sum(len(g.gaps) for g in self.gaps.values()),
                "citations": sum(len(v) for p in self.projects.values() for v in p.chosen.values()),
                "figures": len(self.figures), "reviews": len(self.reviews),
                "tokens_k": round(sum(r.tokens_used for r in recs) / 1000)}


def project_view(p: Project, busy: str | None) -> dict:
    nums = cite.numbering(p)
    return {**json.loads(p.model_dump_json()), "busy": busy, "numbers": nums,
            "markers": {s.id: cite.marker(p, s.id, p.style, nums) for pr in p.draft.paragraphs for s in pr.sentences if p.chosen.get(s.id)},
            "references": cite.references(p, p.style), "style_names": cite.STYLE_NAMES}


def project_summary(p: Project, busy: str | None) -> dict:
    return {"id": p.id, "filename": p.filename, "title": p.draft.title, "created_at": p.created_at,
            "status": p.status, "progress": p.progress, "busy": bool(busy), "claims": len(p.claims),
            "with_sources": len({m.sentence_id for m in p.matches}), "cited": sum(1 for v in p.chosen.values() if v)}


def record_view(r: Record, busy: str | None) -> dict:
    return {**json.loads(r.model_dump_json()), "busy": bool(busy)}


def make_handler(desk: Desk, port: int):
    web = files("paperrepro").joinpath("web")
    shell = web.joinpath("shell.html").read_text()
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

        def _page(self, page: str, script: str, section: str, data: dict | None = None) -> None:
            payload = {"page": page, "section": section, "counts": desk.counts(), "can_run": desk.can_run, **(data or {})}
            blob = json.dumps(payload).replace("</", "<\\/")
            html = shell.replace("/*__APP_DATA__*/null", blob).replace("__PAGE__", script)
            self._send(200, html.encode(), "text/html; charset=utf-8")

        def _file(self, data: bytes, ctype: str, name: str) -> None:
            ascii_name = re.sub(r"[^\w.\- ]+", "", name) or "download"
            self._send(200, data, ctype, {"Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}"})

        def _get(self, store: dict, rid: str):
            return store.get(rid) if ID.match(rid) else None

        # ================================================================ GET
        def do_GET(self) -> None:
            if self.headers.get("Host", "") not in hosts:
                return self._json(403, {"error": "bad host"})
            u = urlparse(self.path)
            path, qs = u.path.rstrip("/") or "/", parse_qs(u.query)
            m = re.fullmatch(r"/static/([\w.]+)", path)
            if m and m.group(1) in STATIC:
                return self._send(200, web.joinpath(m.group(1)).read_bytes(), STATIC[m.group(1)] + "; charset=utf-8")
            if path == "/":
                return self._page("dashboard", "dashboard", "home", {"recent": desk.recent(), "totals": desk.totals()})
            if path == "/gap":
                gaps = sorted(desk.gaps.values(), key=lambda g: -g.created_at)
                return self._page("gaps", "gap", "gap", {"studies": [
                    {"id": g.id, "idea": g.idea, "status": g.status, "progress": g.progress, "created_at": g.created_at,
                     "gaps": len(g.gaps), "papers": len(g.papers)} for g in gaps]})
            if (m := re.fullmatch(r"/gap/([^/]+)", path)) and (g := self._get(desk.gaps, m.group(1))):
                with desk.lock(g.id):
                    return self._page("gap", "gap", "gap", {"study": record_view(g, desk.busy.get(g.id))})
            if path == "/plan":
                (desk.root / ".plan_visited").touch()
                return self._page("plan", "plan", "plan", {"templates": [t.model_dump() for t in templates.TEMPLATES],
                                                            "question": (qs.get("q") or [""])[0][:600]})
            if path == "/figures":
                figs = sorted(desk.figures.values(), key=lambda f: -f.created_at)
                return self._page("figures", "figures", "figures", {"figures": [
                    {"id": f.id, "title": f.title, "status": f.status, "created_at": f.created_at, "chart": f.spec.chart} for f in figs]})
            if (m := re.fullmatch(r"/figures/([^/]+)", path)) and (f := self._get(desk.figures, m.group(1))):
                return self._page("figure", "figures", "figures", {"figure": record_view(f, None)})
            if path == "/cite":
                ps = sorted(desk.projects.values(), key=lambda p: -p.created_at)
                return self._page("cite", "cite", "cite", {"drafts": [project_summary(p, desk.busy.get(p.id)) for p in ps]})
            if (m := re.fullmatch(r"/d/([^/]+)", path)) and (p := self._get(desk.projects, m.group(1))):
                with desk.lock(p.id):
                    return self._page("editor", "cite", "cite", {"project": project_view(p, desk.busy.get(p.id))})
            if path == "/review":
                rs = sorted(desk.reviews.values(), key=lambda r: -r.created_at)
                return self._page("reviews", "review", "review", {"reviews": [
                    {"id": r.id, "title": r.draft.title or r.filename, "status": r.status, "progress": r.progress,
                     "created_at": r.created_at, "recommendation": r.review.recommendation if r.review else ""} for r in rs]})
            if (m := re.fullmatch(r"/review/([^/]+)", path)) and (r := self._get(desk.reviews, m.group(1))):
                with desk.lock(r.id):
                    return self._page("review", "review", "review", {"review": record_view(r, desk.busy.get(r.id))})

            # ---------------------------------------------------------------- API reads
            if path == "/api/drafts":
                return self._json(200, {"drafts": [project_summary(p, desk.busy.get(p.id)) for p in desk.projects.values()]})
            if (m := re.fullmatch(r"/api/d/([^/]+)", path)) and (p := self._get(desk.projects, m.group(1))):
                with desk.lock(p.id):
                    return self._json(200, project_view(p, desk.busy.get(p.id)))
            if (m := re.fullmatch(r"/api/d/([^/]+)/export\.(txt|docx)", path)) and (p := self._get(desk.projects, m.group(1))):
                stem = Path(p.filename).stem[:60] or "draft"
                with desk.lock(p.id):
                    if m.group(2) == "txt":
                        return self._file(cite.to_text(p).encode(), "text/plain; charset=utf-8", f"{stem} (cited).txt")
                    return self._file(cite.to_docx(p), DOCX, f"{stem} (cited).docx")
            for name, store in (("gap", desk.gaps), ("review", desk.reviews), ("figures", desk.figures)):
                if (m := re.fullmatch(rf"/api/{name}/([^/]+)", path)) and (r := self._get(store, m.group(1))):
                    with desk.lock(r.id):
                        return self._json(200, record_view(r, desk.busy.get(r.id)))
            if path == "/api/plan/outline.docx":
                key = (qs.get("t") or ["article"])[0]
                if key not in templates.BY_KEY:
                    return self._json(400, {"error": "unknown template"})
                title, q = (qs.get("title") or [""])[0][:200], (qs.get("q") or [""])[0][:600]
                return self._file(templates.outline_docx(key, title, q), DOCX, f"{title or templates.BY_KEY[key].name} outline.docx")
            return self._json(404, {"error": "not found"})

        # ================================================================ POST
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
            path, body = urlparse(self.path).path, self.rfile.read(n)

            if path in ("/api/upload", "/api/review/upload"):  # raw file body
                if desk.can_run:
                    return self._json(409, {"error": desk.can_run})
                name = unquote(self.headers.get("X-Filename", "draft")).replace("/", "_").replace("\\", "_")[:200]
                if not DOC_EXT.search(name):
                    return self._json(400, {"error": "upload a PDF, a Word file (.docx), or plain text (.txt, .md)"})
                return self._json(201, {"id": self._start(path, name, body)})

            if not self.headers.get("Content-Type", "").startswith("application/json"):
                return self._json(403, {"error": "JSON only"})
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                return self._json(400, {"error": "invalid JSON"})
            if not isinstance(data, dict):
                return self._json(400, {"error": "expected an object"})

            if path in ("/api/paste", "/api/review/paste"):
                if desk.can_run:
                    return self._json(409, {"error": desk.can_run})
                text = str(data.get("text", "")).strip()
                if len(text) < 40:
                    return self._json(400, {"error": "paste at least a few sentences"})
                if len(text) > MAX_TEXT:
                    return self._json(400, {"error": "that is very long; upload it as a file instead"})
                title = re.sub(r"[^\w\-' ]+", "", str(data.get("title", "")))[:60].strip() or "Pasted draft"
                return self._json(201, {"id": self._start(path.replace("paste", "upload"), f"{title}.txt", text.encode())})

            if path == "/api/gap":
                if desk.can_run:
                    return self._json(409, {"error": desk.can_run})
                idea = str(data.get("idea", "")).strip()
                if len(idea) < 15:
                    return self._json(400, {"error": "describe the idea in at least a sentence"})
                if len(idea) > 4000:
                    return self._json(400, {"error": "keep the idea under 4,000 characters"})
                g = GapStudy(idea=idea, progress="Waiting to start")
                with desk.lock(g.id):
                    g.save(desk.root)
                desk.gaps[g.id] = g
                desk.enqueue("gap", g.id)
                return self._json(201, {"id": g.id})

            if path == "/api/figures":
                return self._save_figure(data)
            if (m := re.fullmatch(r"/api/figures/([^/]+)/caption", path)) and (f := self._get(desk.figures, m.group(1))):
                if desk.can_run:
                    return self._json(409, {"error": desk.can_run})
                try:
                    with desk.lock(f.id):
                        desk.jobs["caption"](f, None, desk.root, desk.lock(f.id))
                        return self._json(200, record_view(f, None))
                except Exception as e:
                    return self._json(502, {"error": f"caption failed: {type(e).__name__}"})

            m = re.fullmatch(r"/api/d/([^/]+)/(choose|style|find)", path)
            p = self._get(desk.projects, m.group(1)) if m else None
            if not p:
                return self._json(404, {"error": "not found"})
            return self._project_action(p, m.group(2), data)

        def _start(self, path: str, name: str, data: bytes) -> str:
            if path == "/api/review/upload":
                r = Review(filename=name, progress="Waiting for the reader")
                with desk.lock(r.id):
                    r.save(desk.root)
                desk.reviews[r.id] = r
                desk.enqueue("review", r.id, data)
                return r.id
            p = Project(filename=name or "draft.txt", progress="Waiting for the reader")
            with desk.lock(p.id):
                p.save(desk.root)
            desk.projects[p.id] = p
            desk.enqueue("process", p.id, data)
            return p.id

        def _save_figure(self, data: dict) -> None:
            csv_text = str(data.get("csv", ""))
            if len(csv_text) > figures.MAX_CSV:
                return self._json(413, {"error": "that data is too large for one figure"})
            try:
                spec = FigureSpec.model_validate(data.get("spec") or {})
            except ValidationError as e:
                return self._json(400, {"error": f"invalid chart settings: {e.errors()[0]['msg']}"})
            fid = str(data.get("id", ""))
            f = self._get(desk.figures, fid) if fid else None
            if fid and not f:
                return self._json(404, {"error": "not found"})
            f = f or Figure()
            with desk.lock(f.id):
                f.title = str(data.get("title", "") or "Untitled figure")[:160]
                f.csv, f.spec = csv_text, spec
                if "caption" in data:
                    f.caption = str(data["caption"])[:2000]
                f.save(desk.root)
            desk.figures[f.id] = f
            return self._json(200, record_view(f, None))

        def _project_action(self, p: Project, action: str, data: dict) -> None:
            with desk.lock(p.id):
                if action == "style":
                    if data.get("style") not in STYLES:
                        return self._json(400, {"error": "unknown style"})
                    p.style = data["style"]
                elif action == "choose":
                    sid, src, on = str(data.get("sentence_id", "")), str(data.get("source_id", "")), bool(data.get("on"))
                    if not SID.match(sid) or src not in {mt.source_id for mt in p.matches if mt.sentence_id == sid}:
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
                    desk.enqueue("find", p.id, sid)
                p.save(desk.root)
                return self._json(200, project_view(p, desk.busy.get(p.id)))

    return Handler


def make_jobs(llm) -> dict[str, Callable]:
    from paperrepro import gapfinder, reviewing
    from paperrepro.agents import caption_writer
    from paperrepro.pipeline import find_for_sentence, process
    from paperrepro.trace import Tracer

    def caption(f: Figure, _arg, root: Path, lock) -> None:
        out, t = caption_writer.run(figures.describe(f), llm, Tracer(f.path(root).parent / "trace.jsonl"))
        f.caption, f.alt_text, f.tokens_used = out.caption, out.alt_text, f.tokens_used + t
        f.save(root)

    return {
        "process": lambda p, data, root, lock: process(p, data, llm, root, lock=lock),
        "find": lambda p, sid, root, lock: find_for_sentence(p, sid, llm, root, lock=lock),
        "gap": lambda g, _a, root, lock: gapfinder.run(g, llm, root, lock=lock),
        "review": lambda r, data, root, lock: reviewing.run(r, data, llm, root, lock=lock),
        "caption": caption,
    }


def serve(root: Path, port: int = 8765) -> None:
    from paperrepro.env import load_dotenv
    from paperrepro.llm import LLMError, make_llm

    load_dotenv()
    can_run, llm = "", None
    try:
        llm = make_llm()
    except LLMError as e:
        can_run = f"{e}. Add the key to .env and restart `paperrepro serve`."
    desk = Desk(root, make_jobs(llm), can_run=can_run)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(desk, port))
    state = "ready" if not can_run else "NOT READY: " + can_run
    print(f"PaperRepro: http://127.0.0.1:{port}   [{state}]   Ctrl+C to stop", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
