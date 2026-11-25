from __future__ import annotations

import re

from paperrepro.agents.base import spec
from paperrepro.llm import LLM
from paperrepro.state import CheckedGap, Framing, Landscape, Source, Theme
from paperrepro.trace import Tracer

ABSTRACT_CHARS = 900


def paper_lines(papers: list[Source], prefix: str) -> tuple[str, dict[str, str]]:
    """Number papers P1..Pn for the model; return the text and short id -> real id."""
    lines, ids = [], {}
    for i, s in enumerate(papers, start=1):
        short = f"{prefix}{i}"
        ids[short] = s.id
        abstract = s.abstract[:ABSTRACT_CHARS] if s.abstract else "(no abstract)"
        lines.append(f"[{short}] {s.title} ({s.year or '?'}; {s.venue or 'venue unknown'}; cited {s.cited_by or 0})\n{abstract}")
    return "\n\n".join(lines), ids


def swap_ids(text: str, ids: dict[str, str]) -> str:
    """'P3 and P12 test images' -> '«doi:…» and «doi:…» test images' (whole ids only).
    The page renders each «id» as the paper's title; unknown ids are left as written."""
    return re.sub(r"\b([A-Z]\d+)\b", lambda m: f"«{ids[m.group(1)]}»" if m.group(1) in ids else m.group(1), text)


def run(framing: Framing, idea: str, papers: list[Source], llm: LLM,
        tracer: Tracer) -> tuple[list[Theme], list[CheckedGap], int]:
    text, ids = paper_lines(papers, "P")
    prompt = (f"FIELD: {framing.field}\nIDEA: {idea}\nRESTATED: {framing.summary}\n"
              f"CANDIDATE QUESTIONS:\n- " + "\n- ".join(framing.questions) + f"\n\nPAPERS ({len(papers)}):\n\n{text}")
    out, usage = llm.structured(agent="gap_analyst", system=spec("gap_analyst"), prompt=prompt, schema=Landscape)
    themes, gaps, dropped = [], [], 0
    for t in out.themes:
        t.paper_ids = [ids[i] for i in t.paper_ids if i in ids]
        if t.paper_ids:
            themes.append(t)
    for g in out.gaps:
        ev = [ids[i] for i in g.evidence_ids if i in ids]
        if not ev:  # a gap must point at retrieved papers
            dropped += 1
            continue
        why = swap_ids(g.why_open.replace("[", "").replace("]", ""), ids)
        gaps.append(CheckedGap(**{**g.model_dump(), "evidence_ids": ev, "why_open": why}))
    tracer.event("gap_analyst", papers=len(papers), themes=len(themes), gaps=len(gaps),
                 dropped_without_evidence=dropped, tokens=usage.total, model=usage.model)
    return themes, gaps, usage.total
