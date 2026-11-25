"""Typed models passed between helpers. All inter-agent data goes through these.

A Project is one uploaded draft: its sentences, the sentences worth citing, the real
sources found for them, the judge's verdict on each pairing, and what the person chose.
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------- the draft
class Sentence(BaseModel):
    id: str  # "p3s2" = paragraph 3, sentence 2
    text: str


class Paragraph(BaseModel):
    id: str
    kind: Literal["heading", "body", "references"] = "body"
    sentences: list[Sentence]


class Draft(BaseModel):
    title: str = ""
    paragraphs: list[Paragraph] = Field(default_factory=list)
    ocr_pages: list[int] = Field(default_factory=list)  # 1-based pages read by OCR

    def sentence(self, sid: str) -> Sentence | None:
        return next((s for p in self.paragraphs for s in p.sentences if s.id == sid), None)

    def all_sentences(self) -> list[Sentence]:
        return [s for p in self.paragraphs if p.kind == "body" for s in p.sentences]


# ---------------------------------------------------------------- LLM outputs
class CitableClaim(BaseModel):
    """A sentence that states something a reader would expect a source for."""
    sentence_id: str
    claim: str = Field(description="the claim in a few words, as a reader would search for it")
    queries: list[str] = Field(description="2-3 short keyword searches for scholarly databases")


class ClaimList(BaseModel):
    claims: list[CitableClaim]


class Judgement(BaseModel):
    source_id: str
    verdict: Literal["supports", "related", "unrelated"]
    reason: str = Field(description="one sentence: why, in plain words")
    evidence: str = Field(default="", description="a short quote from the abstract that backs the verdict")


class JudgementList(BaseModel):
    judgements: list[Judgement]


class OcrPage(BaseModel):
    text: str = Field(description="the page's text, verbatim, in reading order")


# ---------------------------------------------------------------- sources
class Source(BaseModel):
    """A real paper returned by a scholarly database. Never written by an LLM."""
    id: str  # stable key: "doi:10.x/y" or "openalex:W123" or "s2:abc"
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str = ""
    doi: str = ""
    url: str = ""
    abstract: str = ""
    cited_by: int | None = None
    found_by: list[str] = Field(default_factory=list)  # "openalex", "semantic_scholar"


class Match(BaseModel):
    sentence_id: str
    source_id: str
    verdict: Literal["supports", "related"]
    reason: str
    evidence: str = ""


# ---------------------------------------------------------------- the project
Status = Literal["queued", "reading", "finding_claims", "searching", "checking", "ready", "error"]
Style = Literal["numbered", "apa", "ieee"]


class Project(BaseModel):
    id: str = Field(default_factory=lambda: time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6])
    filename: str = ""
    created_at: float = Field(default_factory=time.time)
    status: Status = "queued"
    progress: str = ""  # human-readable line for the current step
    error: str = ""
    draft: Draft = Field(default_factory=Draft)
    claims: list[CitableClaim] = Field(default_factory=list)
    sources: dict[str, Source] = Field(default_factory=dict)
    matches: list[Match] = Field(default_factory=list)
    chosen: dict[str, list[str]] = Field(default_factory=dict)  # sentence_id -> source ids, in order
    style: Style = "numbered"
    tokens_used: int = 0

    def dir(self, root: Path) -> Path:
        return root / self.id

    def save(self, root: Path) -> None:
        d = self.dir(root)
        d.mkdir(parents=True, exist_ok=True)
        tmp = d / "project.json.tmp"
        tmp.write_text(self.model_dump_json(indent=1))
        tmp.replace(d / "project.json")  # atomic: readers never see a half-written file

    @classmethod
    def load(cls, path: Path) -> "Project":
        return cls.model_validate(json.loads(path.read_text()))
