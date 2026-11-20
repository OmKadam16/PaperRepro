"""Append-only JSONL trace of every agent step."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class Tracer:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def event(self, agent: str, **data: Any) -> None:
        rec = {"t": round(time.time(), 3), "agent": agent, **data}
        with self.path.open("a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
