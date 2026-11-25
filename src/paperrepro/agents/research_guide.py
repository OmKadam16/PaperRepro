from __future__ import annotations

from paperrepro.agents.base import spec
from paperrepro.llm import LLM
from paperrepro.state import Chat, ChatTurn, GapStudy
from paperrepro.trace import Tracer

HISTORY = 14  # messages the guide sees


def results_text(study: GapStudy | None) -> str:
    if not study or study.status != "ready":
        return ""
    lines = [f"Idea searched: {study.idea}", f"Papers read: {len(study.papers)}"]
    if study.framing:
        lines.append("Candidate questions: " + " | ".join(study.framing.questions))
    if study.themes:
        lines.append("Themes: " + "; ".join(t.name for t in study.themes))
    for i, g in enumerate(study.gaps, start=1):
        lines.append(f"Gap {i} [{g.novelty}] {g.title}: {g.description} Question: {g.question}")
    return "\n".join(lines)


def run(chat: Chat, latest: GapStudy | None, llm: LLM, tracer: Tracer, note: str = "") -> tuple[ChatTurn, int]:
    convo = []
    for m in chat.messages[-HISTORY:]:
        if m.study_id and not m.text:
            convo.append("[search results were shown here]")
        else:
            convo.append(f"{'RESEARCHER' if m.role == 'user' else 'YOU'}: {m.text}")
    prompt = "CONVERSATION:\n" + "\n".join(convo)
    if res := results_text(latest):
        prompt += f"\n\nLATEST SEARCH RESULTS:\n{res}"
    if note:
        prompt += f"\n\nNOTE: {note}"
    out, usage = llm.structured(agent="research_guide", system=spec("research_guide"), prompt=prompt, schema=ChatTurn)
    if out.action == "search" and len(out.search_idea.strip()) < 15:
        out.action = "reply"  # nothing searchable: just talk
    tracer.event("research_guide", action=out.action, idea=out.search_idea[:200], tokens=usage.total, model=usage.model)
    return out, usage.total
