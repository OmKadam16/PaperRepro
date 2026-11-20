"""Minimal .env loader (no dependency). Never logs values. Existing env vars win."""
from __future__ import annotations

import os
import re
from pathlib import Path

LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")
SECRET = re.compile(r"(API_KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL)", re.I)


def load_dotenv(path: Path = Path(".env")) -> list[str]:
    """Set variables from path that are not already set. Returns the names set (not values)."""
    if not path.is_file():
        return []
    names = []
    for raw in path.read_text().splitlines():
        if raw.lstrip().startswith("#") or not (m := LINE.match(raw)):
            continue
        key, val = m.group(1), m.group(2)
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "'\"":
            val = val[1:-1]
        if key not in os.environ:
            os.environ[key] = val
            names.append(key)
    return names


def scrubbed_env(env: dict[str, str]) -> dict[str, str]:
    """Copy of env without secrets, for running untrusted (LLM-written) code."""
    return {k: v for k, v in env.items() if not SECRET.search(k)}
