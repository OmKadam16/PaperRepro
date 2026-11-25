"""Deterministic checks on a draft. Exact numbers the Reviewer is told to trust."""
from __future__ import annotations

import re

from paperrepro.state import Draft, Measures

SECTIONS = {  # canonical name -> heading words that count as it
    "abstract": ("abstract", "summary"),
    "introduction": ("introduction", "background", "motivation"),
    "related work": ("related work", "literature review", "prior work", "state of the art"),
    "methods": ("method", "methods", "methodology", "materials", "approach", "experimental setup", "study design", "data"),
    "results": ("results", "findings", "experiments", "evaluation"),
    "discussion": ("discussion", "limitations", "analysis"),
    "conclusion": ("conclusion", "conclusions", "concluding remarks", "future work"),
    "references": ("references", "bibliography", "works cited"),
}
CORE = ["abstract", "introduction", "methods", "results", "conclusion", "references"]
CITE = re.compile(r"\[\d+(?:\s*[,–-]\s*\d+)*\]|\([A-Z][A-Za-z'\-]+(?: et al\.)?(?:,| and| &)[^()]{0,60}?\d{4}[a-z]?\)")
PASSIVE = re.compile(r"\b(?:is|are|was|were|be|been|being)\s+(?:\w+ly\s+)?\w+(?:ed|en)\b", re.I)


def _section_of(heading: str) -> str | None:
    h = re.sub(r"^[\dIVX.\s]+", "", heading.strip().lower())
    for name, words in SECTIONS.items():
        if any(h == w or h.startswith(w + " ") or h.startswith(w + ":") for w in words):
            return name
    return None


def measure(draft: Draft) -> Measures:
    body = draft.all_sentences()
    words = [len(s.text.split()) for s in body]
    found = []
    for p in draft.paragraphs:
        if p.kind == "heading" and (name := _section_of(p.sentences[0].text)) and name not in found:
            found.append(name)
    if any(p.kind == "references" for p in draft.paragraphs) and "references" not in found:
        found.append("references")
    if "conclusion" not in found and "discussion" in found:
        found_core = set(found) | {"conclusion"}  # a Discussion can close a paper
    else:
        found_core = set(found)
    text = " ".join(s.text for s in body)
    passive = sum(1 for s in body if PASSIVE.search(s.text))
    return Measures(
        words=sum(words), sentences=len(body),
        avg_sentence_words=round(sum(words) / len(words), 1) if words else 0.0,
        long_sentences=sum(1 for w in words if w > 40),
        sections_found=found, sections_missing=[c for c in CORE if c not in found_core],
        has_references="references" in found, citation_markers=len(CITE.findall(text)),
        passive_ratio=round(passive / len(body), 2) if body else 0.0,
    )
