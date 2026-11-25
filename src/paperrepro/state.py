"""Typed models passed between helpers. All inter-agent data goes through these.

A Project is one uploaded draft: its sentences, the sentences worth citing, the real
sources found for them, the judge's verdict on each pairing, and what the person chose.
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import ClassVar, Literal

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
    research_id: str = ""  # the research project (tab) this draft belongs to

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


# ================================================================ shared record storage
class Record(BaseModel):
    """Base for gap studies, reviews and figures: one JSON file per record."""
    id: str = Field(default_factory=lambda: time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6])
    created_at: float = Field(default_factory=time.time)
    status: Literal["queued", "working", "ready", "error"] = "queued"
    progress: str = ""
    error: str = ""
    tokens_used: int = 0
    research_id: str = ""  # the research project (tab) this belongs to; "" for chats/studies

    KIND: ClassVar[str] = "record"

    def path(self, root: Path) -> Path:
        return root / self.KIND / self.id / f"{self.KIND}.json"

    def save(self, root: Path) -> None:
        p = self.path(root)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(self.model_dump_json(indent=1))
        tmp.replace(p)


# ================================================================ stage 1: finding a gap
class Framing(BaseModel):
    """LLM output of the Idea Framer."""
    field: str = Field(description="the research field and sub-field, in a few words")
    summary: str = Field(description="the idea restated precisely in 1-2 sentences")
    questions: list[str] = Field(description="2-4 candidate research questions, specific and answerable")
    queries: list[str] = Field(description="4-6 short keyword searches covering the idea from different angles")
    assumptions: list[str] = Field(default_factory=list, description="anything you had to assume about the idea")


class Theme(BaseModel):
    name: str
    summary: str = Field(description="what this body of work does and finds, 1-2 sentences")
    paper_ids: list[str] = Field(description="ids of the provided papers in this theme")


class Gap(BaseModel):
    title: str
    description: str = Field(description="what is missing, concretely")
    why_open: str = Field(description="why the provided papers leave it open, citing them by id")
    evidence_ids: list[str] = Field(description="ids of provided papers that show the gap")
    question: str = Field(description="a research question that would fill the gap")
    approach: str = Field(description="a feasible way to study it: data, method, comparison")
    kind: Literal["unstudied", "contradictory", "narrow_evidence", "method", "population", "replication"] = "unstudied"


class Landscape(BaseModel):
    """LLM output of the Gap Analyst."""
    themes: list[Theme]
    gaps: list[Gap]


class NoveltyCheck(BaseModel):
    """LLM output of the Novelty Checker for one gap."""
    verdict: Literal["open", "partly_addressed", "addressed"]
    reason: str
    addressing_ids: list[str] = Field(default_factory=list, description="ids of papers that already address it")


class CheckedGap(Gap):
    novelty: Literal["open", "partly_addressed", "addressed", "unchecked"] = "unchecked"
    novelty_reason: str = ""
    addressing_ids: list[str] = Field(default_factory=list)


class GapStudy(Record):
    KIND: ClassVar[str] = "gap"
    idea: str
    framing: Framing | None = None
    papers: dict[str, Source] = Field(default_factory=dict)
    themes: list[Theme] = Field(default_factory=list)
    gaps: list[CheckedGap] = Field(default_factory=list)


# ================================================================ stage 5: review
class CriterionScore(BaseModel):
    criterion: Literal["originality", "clarity", "methods", "evidence", "structure", "significance"]
    score: int = Field(ge=1, le=5, description="1 = serious problems, 3 = acceptable, 5 = excellent")
    comment: str


class ReviewIssue(BaseModel):
    severity: Literal["major", "minor"]
    issue: str
    sentence_ids: list[str] = Field(default_factory=list, description="ids of the sentences concerned, if any")
    fix: str = Field(description="a concrete, actionable fix")


class PeerReview(BaseModel):
    """LLM output of the Reviewer."""
    summary: str = Field(description="what the paper does, in 2-3 sentences, as the reviewer understood it")
    scores: list[CriterionScore]
    strengths: list[str]
    issues: list[ReviewIssue]
    recommendation: Literal["ready", "minor_revision", "major_revision", "not_ready"]


class Measures(BaseModel):
    """Deterministic checks computed by code."""
    words: int = 0
    sentences: int = 0
    avg_sentence_words: float = 0.0
    long_sentences: int = 0  # over 40 words
    sections_found: list[str] = Field(default_factory=list)
    sections_missing: list[str] = Field(default_factory=list)
    has_references: bool = False
    citation_markers: int = 0
    passive_ratio: float = 0.0


class Review(Record):
    KIND: ClassVar[str] = "review"
    filename: str = ""
    draft: Draft = Field(default_factory=Draft)
    measures: Measures | None = None
    review: PeerReview | None = None


# ================================================================ stage 3: figures
class Caption(BaseModel):
    """LLM output of the Caption Writer."""
    caption: str = Field(description="a journal-style figure caption: what is shown, units, n, what the error bars mean")
    alt_text: str = Field(description="a plain description for screen readers")


class FigureSpec(BaseModel):
    chart: Literal["line", "bar", "scatter", "errorbar"] = "line"
    x: str = ""
    ys: list[str] = Field(default_factory=list)
    errors: dict[str, str] = Field(default_factory=dict)  # y column -> its error column
    preset: Literal["single", "double", "thesis", "slide"] = "single"
    palette: Literal["okabe_ito", "grayscale", "viridis"] = "okabe_ito"
    font: Literal["sans", "serif"] = "sans"
    xlabel: str = ""
    ylabel: str = ""
    legend: bool = True
    log_y: bool = False
    fit: bool = False  # least-squares line on scatter plots


class Figure(Record):
    KIND: ClassVar[str] = "figure"
    status: Literal["queued", "working", "ready", "error"] = "ready"
    title: str = "Untitled figure"
    csv: str = ""
    spec: FigureSpec = Field(default_factory=FigureSpec)
    caption: str = ""
    alt_text: str = ""


# ================================================================ chat + research projects
class ChatTurn(BaseModel):
    """LLM output of the Research Guide for one turn."""
    reply: str = Field(description="what you say to the researcher, in plain conversational prose")
    action: Literal["reply", "search"] = Field(description="'search' to run a literature gap search now, else 'reply'")
    search_idea: str = Field(default="", description="for 'search': the idea to search, self-contained and specific")


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    text: str = ""
    study_id: str = ""  # set when this message carries a gap study's results
    at: float = Field(default_factory=time.time)


class Chat(Record):
    KIND: ClassVar[str] = "chat"
    status: Literal["queued", "working", "ready", "error"] = "ready"
    title: str = "New conversation"
    messages: list[ChatMessage] = Field(default_factory=list)


class Research(Record):
    """A research project: one browser-like tab holding its own plan, figures, drafts, reviews."""
    KIND: ClassVar[str] = "research"
    status: Literal["queued", "working", "ready", "error"] = "ready"
    title: str
    question: str = ""
    gap: CheckedGap | None = None
    papers: dict[str, Source] = Field(default_factory=dict)  # the gap's evidence papers
    study_id: str = ""
    chat_id: str = ""
    template: str = "article"
