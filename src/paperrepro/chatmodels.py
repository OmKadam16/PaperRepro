"""Text-only chat models for the project panel: Nemotron 3 Ultra (OpenRouter, free) first,
GLM-4.7-Flash (Z.ai, free, thinking off) when Nemotron fails or is rate-limited.

Keys are read here, on the server, from the environment; they are never sent to the browser,
and provider errors are redacted before they are stored or shown.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass

import httpx

from paperrepro.keys import redact

MODELS = [
    {"name": "Nemotron 3 Ultra", "id": "nvidia/nemotron-3-ultra-550b-a55b:free", "key": "OPENROUTER_API_KEY",
     "url": "https://openrouter.ai/api/v1/chat/completions", "extra": {}, "headers": {"X-Title": "PaperRepro"}},
    {"name": "GLM-4.7-Flash", "id": "glm-4.7-flash", "key": "ZAI_API_KEY",
     "url": "https://api.z.ai/api/paas/v4/chat/completions", "extra": {"thinking": {"type": "disabled"}},
     "headers": {"Accept-Language": "en-US,en"}},
]
MAX_REPLY_TOKENS = 700


class ChatUnavailable(RuntimeError):
    pass


@dataclass
class Reply:
    text: str
    model: str
    tokens: int
    tried: list[str]


def available() -> list[str]:
    return [m["name"] for m in MODELS if os.environ.get(m["key"])]


def complete(system: str, messages: list[dict], client: httpx.Client | None = None) -> Reply:
    """messages: [{'role': 'user'|'assistant', 'content': str}]. Tries each model in order."""
    own = client is None
    client = client or httpx.Client(timeout=60)
    tried: list[str] = []
    try:
        for m in MODELS:
            key = os.environ.get(m["key"])
            if not key:
                continue
            body = {"model": m["id"], "max_tokens": MAX_REPLY_TOKENS, "temperature": 0.4,
                    "messages": [{"role": "system", "content": system}, *messages], **m["extra"]}
            t = time.time()
            try:
                r = client.post(m["url"], json=body, headers={"Authorization": f"Bearer {key}", **m["headers"]})
            except httpx.HTTPError as e:
                tried.append(f"{m['name']}: {type(e).__name__}")
                continue
            if r.status_code != 200:
                tried.append(f"{m['name']}: HTTP {r.status_code}")
                continue
            try:
                d = r.json()
                text = (d["choices"][0]["message"].get("content") or "").strip()
            except (ValueError, KeyError, IndexError):
                tried.append(f"{m['name']}: unreadable reply")
                continue
            if not text:
                tried.append(f"{m['name']}: empty reply")
                continue
            tried.append(f"{m['name']}: ok in {time.time() - t:.1f}s")
            return Reply(text=text, model=m["name"], tokens=(d.get("usage") or {}).get("total_tokens", 0), tried=tried)
        raise ChatUnavailable(redact("; ".join(tried) or "no chat model is configured"))
    finally:
        if own:
            client.close()
