"""Text-only research chat: refuse code requests and prompt attacks before any model is called,
and block code in replies. Deterministic, so it cannot be talked out of its rules."""
from __future__ import annotations

import re

MAX_MESSAGE = 2000

LANGS = (r"python|javascript|typescript|java|kotlin|swift|c\+\+|c#|golang|rust|ruby|php|perl|scala|matlab"
         r"|bash|shell|powershell|sql|html|css|react|node\.?js|django|flask|pandas|numpy|tensorflow|pytorch|latex macro|vba|excel formula")
CODE_REQUEST = re.compile(
    rf"\b(write|generate|implement|debug|refactor|code up|give me|create|fix)\b"
    rf"[^.?!\n]{{0,50}}\b(code|function|snippet|regex|macro|{LANGS})\b"
    rf"|\b({LANGS})\b[^.?!\n]{{0,30}}\b(code|script|snippet|function|program|query)\b"
    rf"|\b(can|could|would) you (please )?(code|program)\b",
    re.I,
)
ATTACK = re.compile(
    r"ignore (all |any |the |your )?(previous|prior|above|earlier) (instructions|rules|prompts?)"
    r"|(reveal|show|print|repeat|leak|dump|tell me)[^.?!\n]{0,30}(system prompt|instructions|your prompt|hidden prompt)"
    r"|\bapi[ _-]?keys?\b|\b(secret|access|bearer|auth) (keys?|tokens?)\b"
    r"|\b(your|the app'?s|the server'?s|the system'?s|admin) (keys?|tokens?|passwords?|credentials|secrets?)\b"
    r"|\.env\b|\benv(ironment)? (file|var(iable)?s?)\b"
    r"|\b(jailbreak|developer mode|DAN mode|act as (an? )?(unrestricted|uncensored))\b"
    r"|\b(os\.environ|process\.env|getenv|/etc/passwd)\b",
    re.I,
)
CODE_SHAPES = re.compile(
    r"```|^\s{0,4}(def |class |import |from \w+ import |#include|public static|function\s*\w*\s*\(|const \w+ ?=|let \w+ ?=|var \w+ ?=|SELECT .+ FROM |<\?php|<script|\$ ?(pip|npm|curl|sudo) )",
    re.I | re.M,
)

REFUSE_CODE = ("I'm here for your research only, so I don't write code. I can help you think through the method, "
               "what to measure, how to describe it, or what the results mean.")
REFUSE_ATTACK = ("I can't help with that. I can only talk about your research: the question, methods, sources, "
                 "figures and writing.")
REFUSE_LONG = f"That message is too long. Please keep it under {MAX_MESSAGE:,} characters."
BLOCKED_REPLY = ("I started to answer with code, which this chat doesn't allow, so I stopped. Ask me about the idea "
                 "behind it instead and I'll explain it in plain words.")


def looks_like_code(text: str) -> bool:
    if CODE_SHAPES.search(text):
        return True
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) >= 3:
        codey = sum(1 for ln in lines if re.search(r"[;{}]\s*$|^\s*[\w.]+\(.*\)\s*;?$|=>|==|!=|\+\+", ln))
        return codey / len(lines) > 0.4
    return False


def check_message(text: str) -> str | None:
    """None if the message may go to a model; otherwise the reply to send instead."""
    if len(text) > MAX_MESSAGE:
        return REFUSE_LONG
    if ATTACK.search(text):
        return REFUSE_ATTACK
    if CODE_REQUEST.search(text) or looks_like_code(text):
        return REFUSE_CODE
    return None


def check_reply(text: str) -> str:
    """Never pass code through, whatever the model produced."""
    return BLOCKED_REPLY if looks_like_code(text) else text
