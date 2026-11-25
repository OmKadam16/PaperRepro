from __future__ import annotations

from paperrepro.agents.base import spec
from paperrepro.agents.gap_analyst import paper_lines, swap_ids
from paperrepro.llm import LLM
from paperrepro.state import CheckedGap, NoveltyCheck, Source
from paperrepro.trace import Tracer


def run(gap: CheckedGap, found: list[Source], llm: LLM, tracer: Tracer) -> tuple[CheckedGap, int]:
    if not found:
        gap.novelty, gap.novelty_reason = "open", "A fresh search found no papers on this question."
        return gap, 0
    text, ids = paper_lines(found, "N")
    prompt = f"GAP: {gap.title}\n{gap.description}\nQUESTION: {gap.question}\n\nPAPERS FOUND:\n\n{text}"
    out, usage = llm.structured(agent="novelty_checker", system=spec("novelty_checker"), prompt=prompt, schema=NoveltyCheck)
    gap.novelty = out.verdict
    gap.addressing_ids = [ids[i] for i in out.addressing_ids if i in ids]
    gap.novelty_reason = swap_ids(out.reason.replace("[", "").replace("]", ""), ids)
    if gap.novelty != "open" and not gap.addressing_ids:
        gap.novelty = "partly_addressed"  # a claim of prior work must name the paper
    tracer.event("novelty_checker", gap=gap.title, candidates=len(found), verdict=gap.novelty,
                 addressing=len(gap.addressing_ids), tokens=usage.total, model=usage.model)
    return gap, usage.total
