"""Keys never leave the server. This module finds them and scrubs them from anything outbound.

Every response body the web server sends passes through `redact`, so even an error message
that quoted a key (or a key-shaped string) reaches the browser as "[redacted]".
"""
from __future__ import annotations

import os
import re
import stat
from pathlib import Path

SECRET_NAME = re.compile(r"(API_KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL)", re.I)
# key-shaped strings from the providers we use, even if they are not in the environment
KEY_SHAPES = re.compile(
    r"\bsk-or-v1-[A-Za-z0-9]{20,}"          # OpenRouter
    r"|\bsk-(?:proj-|svcacct-|ant-)?[A-Za-z0-9_\-]{20,}"  # OpenAI / Anthropic
    r"|\b[0-9a-f]{32}\.[A-Za-z0-9]{16}\b"  # Z.ai / Zhipu
)
REDACTED = "[redacted]"


def secret_values() -> list[str]:
    """Values of every secret-looking environment variable, longest first."""
    vals = [v for k, v in os.environ.items() if SECRET_NAME.search(k) and v and len(v) >= 8]
    return sorted(set(vals), key=len, reverse=True)


def redact(text: str) -> str:
    for v in secret_values():
        if v in text:
            text = text.replace(v, REDACTED)
    return KEY_SHAPES.sub(REDACTED, text)


def redact_bytes(body: bytes) -> bytes:
    """Cheap fast path: only decode and rewrite when something secret-like might be there."""
    vals = secret_values()
    if not any(v.encode() in body for v in vals) and not KEY_SHAPES.search(body.decode("utf-8", "ignore")):
        return body
    return redact(body.decode("utf-8", "replace")).encode("utf-8")


def protect_env_file(path: Path) -> str:
    """Make sure .env is readable by its owner only. Returns a note if anything was fixed."""
    if not path.exists():
        return ""
    mode = path.stat().st_mode
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        return f"{path} was readable by other accounts; it is now owner-only (600)."
    return ""
