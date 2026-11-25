"""PaperRepro web app: `paperrepro serve` -> http://127.0.0.1:8765

Home is a chat with the Research Guide, which finds research gaps. "Start research" on a
gap creates a research project that opens as a tab; each tab has its own tools (overview,
plan, figures, cite, review) holding only that project's work.

Safety: binds 127.0.0.1 only, checks Host and Origin, requires a custom header on every
write (blocks cross-site posts), validates ids, sizes, types; static files are a fixed set.
Keys stay on the server: every text response is scrubbed of key values and key-shaped strings.
Each user gets a strict daily allowance of AI actions (quota.py); chat text is screened (guard.py).
"""
from __future__ import annotations

import json
import math
import queue
import re
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, quote, unquote, urlparse

from pydantic import ValidationError

from paperrepro import chatmodels, cite, figures, guard, templates
from paperrepro.agents.base import spec
from paperrepro.keys import protect_env_file, redact_bytes
from paperrepro.quota import Quota
from paperrepro.state import (
    Chat,
    ChatMessage,
    Figure,
    FigureSpec,
    GapStudy,
    Project,
    Record,
    Research,
    Review,
)
from paperrepro.tools.reader import MAX_BYTES
from paperrepro.trace import Tracer

ID = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{6}$")
SID = re.compile(r"^p\d+s\d+$")
MAX_TEXT = 400_000
MAX_CHAT = guard.MAX_MESSAGE
PANEL_HISTORY = 12
STYLES = ("numbered", "ieee", "apa")
TOOLS = ("overview", "plan", "figures", "cite", "review")
STATIC = {name: ("text/css" if name.endswith(".css") else "text/javascript") for name in
          ("app.css", "core.js", "chat.js", "research.js", "plan.js", "figures.js", "cite.js", "review.js", "panel.js")}
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
DOC_EXT = re.compile(r"\.(pdf|docx|txt|md|markdown|tex)$", re.I)
EARLIER = "Earlier work"


class Desk:
    """All records in memory (the source of truth while running) plus one AI job worker."""

    def __init__(self, root: Path, jobs: dict[str, Callable], can_run: str = "",
                 quota: Quota | None = None, complete: Callable = chatmodels.complete):
        self.root, self.jobs, self.can_run = root, jobs, can_run
        root.mkdir(parents=True, exist_ok=True)
        self.quota = quota or Quota(root)
        self.complete = complete  # text-only chat models for the project panel
        self.projects: dict[str, Project] = {}
        self.gaps: dict[str, GapStudy] = {}
        self.reviews: dict[str, Review] = {}
        self.figures: dict[str, Figure] = {}
        self.chats: dict[str, Chat] = {}
        self.research: dict[str, Research] = {}
        self.tabs: list[str] = []
        self.locks: dict[str, threading.RLock] = {}
        self.busy: dict[str, str] = {}
        self.q: queue.Queue = queue.Queue()
        self.guard = threading.Lock()
        root.mkdir(parents=True, exist_ok=True)
        self._load()
        threading.Thread(target=self._work, daemon=True).start()

    # ---------------------------------------------------------------- persistence
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
        for cls, store in ((GapStudy, self.gaps), (Review, self.reviews), (Figure, self.figures),
                           (Chat, self.chats), (Research, self.research)):
            for f in sorted((self.root / cls.KIND).glob(f"*/{cls.KIND}.json")):
                try:
                    r = cls.model_validate_json(f.read_text())
                except Exception:
                    continue
                if r.status in ("queued", "working"):
                    r.status, r.error = "error", stopped
                store[r.id] = r
        tabs = self.root / "tabs.json"
        if tabs.exists():
            try:
                self.tabs = [t for t in json.loads(tabs.read_text()) if t in self.research]
            except (json.JSONDecodeError, TypeError):
                self.tabs = []
        self._adopt_orphans()

    def _adopt_orphans(self) -> None:
        """Work made before research tabs existed goes into one 'Earlier work' project."""
        orphans = [r for r in (*self.projects.values(), *self.figures.values(), *self.reviews.values()) if not r.research_id]
        if not orphans:
            return
        home = next((r for r in self.research.values() if r.title == EARLIER), None)
        if home is None:
            home = Research(title=EARLIER, question="Drafts, figures and reviews made before research projects existed.")
            home.save(self.root)
            self.research[home.id] = home
        for r in orphans:
            r.research_id = home.id
            r.save(self.root)

    def save_tabs(self) -> None:
        (self.root / "tabs.json").write_text(json.dumps(self.tabs))

    def open_tab(self, rid: str) -> None:
        if rid in self.research and rid not in self.tabs:
            self.tabs.append(rid)
            self.save_tabs()

    def lock(self, rid: str) -> threading.RLock:
        with self.guard:
            return self.locks.setdefault(rid, threading.RLock())

    # ---------------------------------------------------------------- jobs
    def enqueue(self, kind: str, rid: str, arg=None) -> None:
        self.busy[rid] = kind if kind != "find" else f"find:{arg}"
        self.q.put((kind, rid, arg))

    def _work(self) -> None:
        stores = {"process": self.projects, "find": self.projects, "gap": self.gaps, "review": self.reviews, "chat": self.chats}
        while True:
            kind, rid, arg = self.q.get()
            rec = stores[kind][rid]
            try:
                self.jobs[kind](rec, arg, self.root, self.lock(rid))
            except Exception as e:
                rec.status, rec.error = "error", f"{type(e).__name__}: {e}"
                traceback.print_exc()
            finally:
                self.busy.pop(rid, None)

    # ---------------------------------------------------------------- views
    def research_counts(self, rid: str) -> dict:
        return {"figures": sum(f.research_id == rid for f in self.figures.values()),
                "drafts": sum(p.research_id == rid for p in self.projects.values()),
                "citations": sum(len(v) for p in self.projects.values() if p.research_id == rid for v in p.chosen.values()),
                "reviews": sum(r.research_id == rid for r in self.reviews.values())}

    def shell(self) -> dict:
        """What every page needs: open tabs, research list, recent chats."""
        rs = sorted(self.research.values(), key=lambda r: -r.created_at)
        cs = sorted((c for c in self.chats.values() if not c.research_id), key=lambda c: -(c.messages[-1].at if c.messages else c.created_at))
        return {"tabs": [{"id": t, "title": self.research[t].title} for t in self.tabs],
                "researches": [{"id": r.id, "title": r.title, "question": r.question, "created_at": r.created_at,
                                "open": r.id in self.tabs, **self.research_counts(r.id)} for r in rs],
                "chats": [{"id": c.id, "title": c.title, "created_at": c.created_at, "busy": bool(self.busy.get(c.id))} for c in cs[:30]],
                "can_run": self.can_run}

    def panel_chat(self, rid: str) -> Chat:
        """The side-panel conversation of one research project (one per project)."""
        c = next((c for c in self.chats.values() if c.research_id == rid), None)
        if c is None:
            c = Chat(research_id=rid, title="Project assistant")
            self.chats[c.id] = c
        return c

    def panel_system(self, res: Research) -> str:
        n = self.research_counts(res.id)
        lines = [spec("project_assistant"), "", "## This project", f"Title: {res.title}"]
        if res.question:
            lines.append(f"Research question: {res.question}")
        if res.gap:
            g = res.gap
            lines += [f"The gap it fills: {g.title}. {g.description}", f"Suggested approach: {g.approach}",
                      f"Novelty check: {g.novelty.replace('_', ' ')}"]
        t = templates.BY_KEY.get(res.template)
        if t:
            lines.append(f"Paper template: {t.name}")
        lines.append(f"Work so far: {n['figures']} figures, {n['drafts']} drafts in Cite with {n['citations']} citations, "
                     f"{n['reviews']} reviews.")
        return "\n".join(lines)

    def chat_view(self, c: Chat) -> dict:
        studies = {m.study_id: record_view(self.gaps[m.study_id], self.busy.get(m.study_id))
                   for m in c.messages if m.study_id and m.study_id in self.gaps}
        started = {r.study_id + ":" + (r.gap.title if r.gap else ""): r.id for r in self.research.values() if r.study_id}
        return {**json.loads(c.model_dump_json()), "busy": bool(self.busy.get(c.id)), "studies": studies, "started": started}


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

        def _ident(self) -> None:
            """Who is asking, for the daily allowance: a signed cookie plus the network address."""
            self.ip = self.client_address[0]
            m = re.search(r"(?:^|;\s*)pr_uid=([0-9a-f]{24}\.[0-9a-f]{24})", self.headers.get("Cookie", ""))
            self.uid = desk.quota.verify(m.group(1)) if m else None
            self.new_cookie = None
            if not self.uid:
                self.new_cookie = desk.quota.new_user()
                self.uid = desk.quota.verify(self.new_cookie)

        def _quota(self) -> dict:
            return desk.quota.status(self.uid, self.ip)

        def _spend(self) -> bool:
            """Take one AI action from today's allowance, or answer 429 and return False."""
            if desk.quota.take(self.uid, self.ip):
                return True
            q = self._quota()
            left = max(60, datetime_seconds_until(q["resets_at"]))
            h, mnt = divmod(math.ceil(left / 60), 60)
            when = f"{h} h {mnt} min" if h else f"{mnt} min"
            self._json(429, {"error": f"You've used all {q['limit']} AI calls for today. They reset at midnight UTC, in {when}.",
                             "quota": q})
            return False

        def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None) -> None:
            if ctype.startswith(("text/", "application/json")):
                body = redact_bytes(body)  # never let a key reach the browser, even inside an error
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Cache-Control", "no-store")
            if getattr(self, "new_cookie", None):
                self.send_header("Set-Cookie", f"pr_uid={self.new_cookie}; Path=/; HttpOnly; SameSite=Strict; Max-Age=31536000")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, data) -> None:
            self._send(code, json.dumps(data).encode(), "application/json")

        def _page(self, page: str, script: str, data: dict | None = None, research: Research | None = None, tool: str = "") -> None:
            if research:
                desk.open_tab(research.id)
            payload = {"page": page, **desk.shell(), "tool": tool, "quota": self._quota(), **(data or {})}
            if research:
                payload["research"] = {**record_view(research, None), **desk.research_counts(research.id)}
            blob = json.dumps(payload).replace("</", "<\\/")
            self._send(200, shell.replace("/*__APP_DATA__*/null", blob).replace("__PAGE__", script).encode(), "text/html; charset=utf-8")

        def _file(self, data: bytes, ctype: str, name: str) -> None:
            ascii_name = re.sub(r"[^\w.\- ]+", "", name) or "download"
            self._send(200, data, ctype, {"Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}"})

        def _get(self, store: dict, rid: str):
            return store.get(rid) if ID.match(rid or "") else None

        def _owned(self, store: dict, rid: str, research: Research):
            r = self._get(store, rid)
            return r if r is not None and r.research_id == research.id else None

        # ================================================================ GET
        def do_GET(self) -> None:
            if self.headers.get("Host", "") not in hosts:
                return self._json(403, {"error": "bad host"})
            self._ident()
            u = urlparse(self.path)
            path, qs = u.path.rstrip("/") or "/", parse_qs(u.query)
            if (m := re.fullmatch(r"/static/([\w.]+)", path)) and m.group(1) in STATIC:
                return self._send(200, web.joinpath(m.group(1)).read_bytes(), STATIC[m.group(1)] + "; charset=utf-8")
            if path == "/":
                return self._page("chat", "chat", {"chat": None})
            if (m := re.fullmatch(r"/chat/([^/]+)", path)) and (c := self._get(desk.chats, m.group(1))):
                with desk.lock(c.id):
                    return self._page("chat", "chat", {"chat": desk.chat_view(c)})
            if m := re.fullmatch(r"/r/([^/]+)(?:/(.*))?", path):
                res = self._get(desk.research, m.group(1))
                if res:
                    return self._research_page(res, m.group(2) or "")
            if path.startswith("/api/"):
                return self._api_get(path, qs)
            return self._json(404, {"error": "not found"})

        def _research_page(self, res: Research, rest: str) -> None:
            mine = lambda store: sorted((x for x in store.values() if x.research_id == res.id), key=lambda x: -x.created_at)  # noqa: E731
            if rest in ("", "overview"):
                return self._page("research", "research", {}, res, "overview")
            if rest == "plan":
                return self._page("plan", "plan", {"templates": [t.model_dump() for t in templates.TEMPLATES]}, res, "plan")
            if rest == "figures":
                return self._page("figures", "figures", {"figures": [{"id": f.id, "title": f.title, "status": f.status,
                                  "created_at": f.created_at, "chart": f.spec.chart} for f in mine(desk.figures)]}, res, "figures")
            if (m := re.fullmatch(r"figures/([^/]+)", rest)) and (f := self._owned(desk.figures, m.group(1), res)):
                return self._page("figure", "figures", {"figure": record_view(f, None)}, res, "figures")
            if rest == "cite":
                return self._page("cite", "cite", {"drafts": [project_summary(p, desk.busy.get(p.id)) for p in mine(desk.projects)]}, res, "cite")
            if (m := re.fullmatch(r"d/([^/]+)", rest)) and (p := self._owned(desk.projects, m.group(1), res)):
                with desk.lock(p.id):
                    return self._page("editor", "cite", {"project": project_view(p, desk.busy.get(p.id))}, res, "cite")
            if rest == "review":
                return self._page("reviews", "review", {"reviews": [{"id": r.id, "title": r.draft.title or r.filename, "status": r.status,
                                  "progress": r.progress, "created_at": r.created_at,
                                  "recommendation": r.review.recommendation if r.review else ""} for r in mine(desk.reviews)]}, res, "review")
            if (m := re.fullmatch(r"review/([^/]+)", rest)) and (r := self._owned(desk.reviews, m.group(1), res)):
                with desk.lock(r.id):
                    return self._page("review", "review", {"review": record_view(r, desk.busy.get(r.id))}, res, "review")
            return self._json(404, {"error": "not found"})

        def _api_get(self, path: str, qs: dict) -> None:
            if (m := re.fullmatch(r"/api/chat/([^/]+)", path)) and (c := self._get(desk.chats, m.group(1))):
                with desk.lock(c.id):
                    return self._json(200, desk.chat_view(c))
            if path == "/api/shell":
                return self._json(200, desk.shell())
            if path == "/api/quota":
                return self._json(200, self._quota())
            if (m := re.fullmatch(r"/api/r/([^/]+)/chat", path)) and (res := self._get(desk.research, m.group(1))):
                return self._json(200, self._panel_view(res))
            if (m := re.fullmatch(r"/api/d/([^/]+)", path)) and (p := self._get(desk.projects, m.group(1))):
                with desk.lock(p.id):
                    return self._json(200, project_view(p, desk.busy.get(p.id)))
            if (m := re.fullmatch(r"/api/d/([^/]+)/export\.(txt|docx)", path)) and (p := self._get(desk.projects, m.group(1))):
                stem = Path(p.filename).stem[:60] or "draft"
                with desk.lock(p.id):
                    if m.group(2) == "txt":
                        return self._file(cite.to_text(p).encode(), "text/plain; charset=utf-8", f"{stem} (cited).txt")
                    return self._file(cite.to_docx(p), DOCX, f"{stem} (cited).docx")
            for name, store in (("gap", desk.gaps), ("review", desk.reviews), ("figures", desk.figures), ("r", desk.research)):
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
            self._ident()
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
                res = self._get(desk.research, self.headers.get("X-Research", ""))
                if not res:
                    return self._json(400, {"error": "open a research project first"})
                name = unquote(self.headers.get("X-Filename", "draft")).replace("/", "_").replace("\\", "_")[:200]
                if not DOC_EXT.search(name):
                    return self._json(400, {"error": "upload a PDF, a Word file (.docx), or plain text (.txt, .md)"})
                if not self._spend():
                    return
                return self._json(201, {"id": self._start(path, name, body, res)})

            if not self.headers.get("Content-Type", "").startswith("application/json"):
                return self._json(403, {"error": "JSON only"})
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                return self._json(400, {"error": "invalid JSON"})
            if not isinstance(data, dict):
                return self._json(400, {"error": "expected an object"})

            if path == "/api/chat":
                return self._chat(data)
            if (m := re.fullmatch(r"/api/r/([^/]+)/chat", path)) and (res := self._get(desk.research, m.group(1))):
                return self._panel(res, data)
            if path == "/api/research":
                return self._start_research(data)
            if path == "/api/tabs/close":
                rid = str(data.get("id", ""))
                desk.tabs = [t for t in desk.tabs if t != rid]
                desk.save_tabs()
                return self._json(200, desk.shell())
            if (m := re.fullmatch(r"/api/r/([^/]+)", path)) and (res := self._get(desk.research, m.group(1))):
                with desk.lock(res.id):
                    if "title" in data:
                        res.title = str(data["title"]).strip()[:160] or res.title
                    if "question" in data:
                        res.question = str(data["question"]).strip()[:800]
                    if data.get("template") in templates.BY_KEY:
                        res.template = data["template"]
                    res.save(desk.root)
                    return self._json(200, {**record_view(res, None), **desk.research_counts(res.id)})

            if path in ("/api/paste", "/api/review/paste"):
                if desk.can_run:
                    return self._json(409, {"error": desk.can_run})
                res = self._get(desk.research, str(data.get("research_id", "")))
                if not res:
                    return self._json(400, {"error": "open a research project first"})
                text = str(data.get("text", "")).strip()
                if len(text) < 40:
                    return self._json(400, {"error": "paste at least a few sentences"})
                if len(text) > MAX_TEXT:
                    return self._json(400, {"error": "that is very long; upload it as a file instead"})
                title = re.sub(r"[^\w\-' ]+", "", str(data.get("title", "")))[:60].strip() or "Pasted draft"
                if not self._spend():
                    return
                return self._json(201, {"id": self._start(path.replace("paste", "upload"), f"{title}.txt", text.encode(), res)})

            if path == "/api/figures":
                return self._save_figure(data)
            if (m := re.fullmatch(r"/api/figures/([^/]+)/caption", path)) and (f := self._get(desk.figures, m.group(1))):
                if desk.can_run:
                    return self._json(409, {"error": desk.can_run})
                if not self._spend():
                    return
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

        # ---------------------------------------------------------------- actions
        def _chat(self, data: dict) -> None:
            if desk.can_run:
                return self._json(409, {"error": desk.can_run})
            text = str(data.get("text", "")).strip()
            if not text:
                return self._json(400, {"error": "type a message"})
            if len(text) > MAX_CHAT:
                return self._json(400, {"error": f"keep messages under {MAX_CHAT:,} characters"})
            cid = str(data.get("chat_id", ""))
            c = self._get(desk.chats, cid) if cid else None
            if cid and not c:
                return self._json(404, {"error": "not found"})
            if c and c.research_id:
                return self._json(404, {"error": "not found"})
            if c and desk.busy.get(c.id):
                return self._json(409, {"error": "still thinking about your last message"})
            refusal = guard.check_message(text)
            if not refusal and not self._spend():
                return
            c = c or Chat()
            with desk.lock(c.id):
                c.messages.append(ChatMessage(role="user", text=text))
                if refusal:  # answered by the server itself: no model call, no allowance spent
                    c.messages.append(ChatMessage(role="assistant", text=refusal))
                    if c.title == "New conversation":
                        c.title = text[:70]
                else:
                    c.status = "queued"
                c.save(desk.root)
            desk.chats[c.id] = c
            if not refusal:
                desk.enqueue("chat", c.id, desk.gaps)
            return self._json(200, {**desk.chat_view(c), "quota": self._quota()})

        # ---------------------------------------------------------------- project panel
        def _panel_view(self, res: Research) -> dict:
            c = next((c for c in desk.chats.values() if c.research_id == res.id), None)
            return {"messages": [m.model_dump() for m in c.messages] if c else [], "busy": bool(c and desk.busy.get(c.id)),
                    "models": chatmodels.available(), "quota": self._quota()}

        def _panel(self, res: Research, data: dict) -> None:
            text = str(data.get("text", "")).strip()
            if not text:
                return self._json(400, {"error": "type a message"})
            if not chatmodels.available():
                return self._json(409, {"error": "The project chat isn't set up: add OPENROUTER_API_KEY or ZAI_API_KEY to .env and restart."})
            with desk.guard:
                c = desk.panel_chat(res.id)
                if desk.busy.get(c.id):
                    return self._json(409, {"error": "still answering your last message"})
                desk.busy[c.id] = "panel"
            try:
                refusal = guard.check_message(text)
                if refusal:
                    with desk.lock(c.id):
                        c.messages += [ChatMessage(role="user", text=text[:MAX_CHAT]), ChatMessage(role="assistant", text=refusal)]
                        c.save(desk.root)
                    return self._json(200, {**self._panel_view(res), "busy": False, "model": "", "refused": True})
                if not self._spend():
                    return
                history = [{"role": m.role, "content": m.text} for m in c.messages[-PANEL_HISTORY:] if m.text]
                tracer, t0 = Tracer(c.path(desk.root).parent / "trace.jsonl"), time.time()
                try:
                    reply = desk.complete(desk.panel_system(res), [*history, {"role": "user", "content": text}])
                except chatmodels.ChatUnavailable as e:
                    desk.quota.refund(self.uid, self.ip)
                    tracer.event("project_assistant", error=str(e), seconds=round(time.time() - t0, 2))
                    return self._json(503, {"error": "Both chat models are busy right now (this didn't use a call). Try again in a minute.",
                                            "quota": self._quota()})
                answer = guard.check_reply(reply.text)
                tracer.event("project_assistant", model=reply.model, tried=reply.tried, tokens=reply.tokens,
                             blocked=answer != reply.text, seconds=round(time.time() - t0, 2))
                with desk.lock(c.id):
                    c.messages += [ChatMessage(role="user", text=text), ChatMessage(role="assistant", text=answer)]
                    c.tokens_used += reply.tokens
                    c.save(desk.root)
                return self._json(200, {**self._panel_view(res), "busy": False, "model": reply.model})
            finally:
                desk.busy.pop(c.id, None)

        def _start_research(self, data: dict) -> None:
            study = self._get(desk.gaps, str(data.get("study_id", "")))
            try:
                i = int(data.get("gap", -1))
            except (TypeError, ValueError):
                i = -1
            if not study or not 0 <= i < len(study.gaps):
                return self._json(400, {"error": "pick a gap from a finished search"})
            gap = study.gaps[i]
            existing = next((r for r in desk.research.values() if r.study_id == study.id and r.gap and r.gap.title == gap.title), None)
            if existing:
                desk.open_tab(existing.id)
                return self._json(200, {"id": existing.id})
            keep = set(gap.evidence_ids) | set(gap.addressing_ids)
            res = Research(title=gap.title[:160], question=gap.question, gap=gap, study_id=study.id,
                           chat_id=str(data.get("chat_id", ""))[:40],
                           papers={k: v for k, v in study.papers.items() if k in keep})
            with desk.lock(res.id):
                res.save(desk.root)
            desk.research[res.id] = res
            desk.open_tab(res.id)
            return self._json(201, {"id": res.id})

        def _start(self, path: str, name: str, data: bytes, res: Research) -> str:
            if path == "/api/review/upload":
                r = Review(filename=name, progress="Waiting for the reader", research_id=res.id)
                with desk.lock(r.id):
                    r.save(desk.root)
                desk.reviews[r.id] = r
                desk.enqueue("review", r.id, data)
                return r.id
            p = Project(filename=name or "draft.txt", progress="Waiting for the reader", research_id=res.id)
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
            if not f:
                res = self._get(desk.research, str(data.get("research_id", "")))
                if not res:
                    return self._json(400, {"error": "open a research project first"})
                f = Figure(research_id=res.id)
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
                    if not self._spend():
                        return
                    desk.enqueue("find", p.id, sid)
                p.save(desk.root)
                return self._json(200, project_view(p, desk.busy.get(p.id)))

    return Handler


def make_jobs(llm) -> dict[str, Callable]:
    from paperrepro import chatting, gapfinder, reviewing
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
        "chat": lambda c, studies, root, lock: chatting.turn(c, llm, root, studies,
                                                             lambda s: gapfinder.run(s, llm, root), lock=lock),
        "caption": caption,
    }


def datetime_seconds_until(iso: str) -> float:
    from datetime import datetime
    return (datetime.fromisoformat(iso) - datetime.now(datetime.fromisoformat(iso).tzinfo)).total_seconds()


def serve(root: Path, port: int = 8765) -> None:
    from paperrepro.env import load_dotenv
    from paperrepro.llm import LLMError, make_llm

    note = protect_env_file(Path(".env"))
    if note:
        print(note, flush=True)
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
