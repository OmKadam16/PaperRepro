from __future__ import annotations

from pathlib import Path

AGENTS_DIR = Path(__file__).resolve().parents[3] / "agents"


def spec(name: str) -> str:
    """Load an agent's markdown spec; it is the system prompt."""
    return (AGENTS_DIR / f"{name}.md").read_text()
