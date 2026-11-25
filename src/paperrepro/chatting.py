"""One chat turn: the Research Guide replies, and may run a gap study whose cards appear in
the conversation; when the study finishes, the guide comments on the results."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable

from paperrepro.agents import research_guide
from paperrepro.llm import LLM
from paperrepro.state import Chat, ChatMessage, GapStudy
from paperrepro.trace import Tracer


def latest_study(chat: Chat, studies: dict[str, GapStudy]) -> GapStudy | None:
    for m in reversed(chat.messages):
        if m.study_id and m.study_id in studies:
            return studies[m.study_id]
    return None


def turn(chat: Chat, llm: LLM, root: Path, studies: dict[str, GapStudy],
         run_study: Callable[[GapStudy], GapStudy], lock: threading.RLock | None = None) -> Chat:
    lock = lock or threading.RLock()
    tracer = Tracer(chat.path(root).parent / "trace.jsonl")

    def save() -> None:
        with lock:
            chat.save(root)

    try:
        chat.status = "working"
        save()
        out, t = research_guide.run(chat, latest_study(chat, studies), llm, tracer)
        with lock:
            chat.tokens_used += t
            chat.messages.append(ChatMessage(role="assistant", text=out.reply))
            if chat.title == "New conversation":
                first = next((m.text for m in chat.messages if m.role == "user"), "")
                chat.title = (first[:70] + "…") if len(first) > 70 else first or chat.title
        save()
        if out.action == "search":
            study = GapStudy(idea=out.search_idea.strip(), progress="Waiting to start")
            study.save(root)
            studies[study.id] = study
            with lock:
                chat.messages.append(ChatMessage(role="assistant", study_id=study.id))
            save()
            run_study(study)
            note = (f"The search finished: {len(study.gaps)} gaps from {len(study.papers)} papers. Comment on them."
                    if study.status == "ready" else f"The search failed ({study.error}). Apologise briefly and suggest rephrasing.")
            out2, t2 = research_guide.run(chat, study if study.status == "ready" else None, llm, tracer, note=note)
            with lock:
                chat.tokens_used += t2
                chat.messages.append(ChatMessage(role="assistant", text=out2.reply))
        with lock:
            chat.status = "ready"
    except Exception as e:
        with lock:
            chat.status, chat.error = "error", f"{type(e).__name__}: {e}"
            chat.messages.append(ChatMessage(role="assistant", text="Sorry, something went wrong on my side. Please try again."))
        tracer.event("chat", error=chat.error)
    save()
    return chat
