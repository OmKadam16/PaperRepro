"""Split paragraphs into sentences, conservatively. No network, no LLM.

A wrong split puts a citation in the middle of a sentence, so this errs towards keeping
text together: it only breaks after . ! ? followed by a capital, digit, quote or bracket,
and never after common abbreviations, initials or decimals.
"""
from __future__ import annotations

import re

from paperrepro.state import Draft, Paragraph, Sentence

ABBREV = {
    "e.g", "i.e", "et al", "al", "fig", "figs", "eq", "eqs", "vs", "cf", "etc", "approx",
    "dr", "mr", "mrs", "ms", "prof", "no", "nos", "vol", "pp", "p", "sec", "ch", "tab",
    "ref", "refs", "resp", "ca", "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep",
    "sept", "oct", "nov", "dec", "inc", "ltd", "co", "st", "u.s", "u.k", "ph.d",
}
REF_HEADINGS = re.compile(r"^\s*(\d+(\.\d+)*\s+)?(references|bibliography|works cited|literature cited)\s*$", re.I)
_BOUNDARY = re.compile(r"[.!?][\"'”’)\]]*\s+(?=[A-Z0-9\"'“‘(\[])")


def split_sentences(text: str) -> list[str]:
    out, start = [], 0
    for m in _BOUNDARY.finditer(text):
        end = m.end()
        before = text[start:m.start() + 1].rstrip()
        word = re.search(r"([A-Za-z][A-Za-z.]*)\.$", before)
        if word:
            w = word.group(1).lower().rstrip(".")
            if w in ABBREV or len(w) == 1:  # abbreviation or an initial like "J."
                continue
        out.append(text[start:end].strip())
        start = end
    tail = text[start:].strip()
    if tail:
        out.append(tail)
    return [s for s in out if s]


def build_draft(blocks: list[tuple[str, str]]) -> Draft:
    """blocks: (kind, text) where kind is heading|body. Paragraphs after a References heading
    are kept for export but marked so they are never searched for citations."""
    draft, in_refs = Draft(), False
    for i, (kind, text) in enumerate(blocks):
        pid = f"p{i + 1}"
        if kind == "heading":
            in_refs = bool(REF_HEADINGS.match(text))
            draft.paragraphs.append(Paragraph(id=pid, kind="heading", sentences=[Sentence(id=f"{pid}s1", text=text)]))
            if not draft.title and i < 3:
                draft.title = text
            continue
        parts = [text] if in_refs else split_sentences(text)
        draft.paragraphs.append(Paragraph(
            id=pid, kind="references" if in_refs else "body",
            sentences=[Sentence(id=f"{pid}s{j + 1}", text=t) for j, t in enumerate(parts)]))
    return draft
