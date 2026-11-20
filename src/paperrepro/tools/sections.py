"""Cut raw paper text into sections at LLM-identified headings, keeping the text verbatim.

The LLM only says where sections start; it never rewrites section text, so numbers and
method details cannot be summarized away or altered.
"""
from __future__ import annotations

import re

from paperrepro.state import Section

DECIMAL = re.compile(r"-?\d+\.\d+")


def _heading_re(heading: str) -> re.Pattern[str]:
    toks = [re.escape(t) for t in heading.split()]
    # PDF extraction often breaks "3.1 Evaluation" across lines or drops spaces
    return re.compile(r"(?:^|\n)\s*" + r"\s*".join(toks), re.I)


def slice_sections(raw: str, headings: list[str]) -> tuple[list[Section], list[str]]:
    """Sections in document order, plus headings that could not be located."""
    found: list[tuple[int, int, str]] = []
    missing: list[str] = []
    cursor = 0
    for h in headings:
        if not h.strip():
            continue
        m = _heading_re(h).search(raw, cursor)
        if not m:
            missing.append(h)
            continue
        found.append((m.start(), m.end(), h.strip()))
        cursor = m.end()
    if not found:
        return [Section(heading="Full text", text=raw.strip())], missing
    out = []
    if found[0][0] > 0 and raw[: found[0][0]].strip():
        out.append(Section(heading="Front matter", text=raw[: found[0][0]].strip()))
    for i, (_, end, h) in enumerate(found):
        stop = found[i + 1][0] if i + 1 < len(found) else len(raw)
        out.append(Section(heading=h, text=raw[end:stop].strip()))
    return out, missing


def unverified_numbers(tables: list[str], raw: str) -> list[str]:
    """Decimal numbers in LLM-transcribed tables that do not occur in the raw text."""
    norm = raw.replace("−", "-").replace("–", "-")
    seen = set(DECIMAL.findall(norm)) | {n.lstrip("-") for n in DECIMAL.findall(norm)}
    bad = []
    for t in tables:
        for n in DECIMAL.findall(t.replace("−", "-")):
            if n not in seen and n.lstrip("-") not in seen:
                bad.append(n)
    return sorted(set(bad))
