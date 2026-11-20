"""Typed models passed between agents. All inter-agent data goes through these."""
from __future__ import annotations

import json
import time
import uuid
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class Section(BaseModel):
    heading: str
    text: str


class Paper(BaseModel):
    title: str
    source_url: str = ""
    authors: list[str] = Field(default_factory=list)
    sections: list[Section] = Field(default_factory=list)
    tables: list[str] = Field(default_factory=list)
    figure_captions: list[str] = Field(default_factory=list)
    data_links: list[str] = Field(default_factory=list)
    code_links: list[str] = Field(default_factory=list)
    notes: str = ""


class Claim(BaseModel):
    id: str
    description: str
    metric: str
    paper_value: float
    tolerance: float = 0.05
    tolerance_type: Literal["abs", "rel"] = "rel"
    source: str = ""
    feasible: bool = True
    infeasible_reason: str = ""


class ReproSpec(BaseModel):
    claims: list[Claim]
    datasets: list[str] = Field(default_factory=list)
    preprocessing: list[str] = Field(default_factory=list)
    models_or_methods: list[str] = Field(default_factory=list)
    evaluation: list[str] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)


class DatasetRef(BaseModel):
    name: str
    source: Literal["geo", "physionet", "zenodo", "huggingface", "github", "url", "other"] = "url"
    url: str = ""
    accession: str = ""
    size_mb: float | None = None
    license: str = ""
    # too_large: resolves, but exceeds Budget.max_data_mb, so not downloaded
    status: Literal["available", "restricted", "missing", "too_large"] = "available"
    is_substitute: bool = False
    download_plan: str = ""
    # Set by code after verification, never by the LLM:
    verified: bool = False
    verify_note: str = ""
    local_paths: list[str] = Field(default_factory=list)  # relative to the workspace


class DatasetList(BaseModel):
    items: list[DatasetRef]


class CodeBundle(BaseModel):
    """Files the Coder writes into the run workspace. Paths are relative."""
    files: dict[str, str]
    notes: str = ""


class ExecResult(BaseModel):
    exit_code: int
    stdout_tail: str = ""
    stderr_tail: str = ""
    duration_s: float = 0.0
    metrics: dict[str, float] = Field(default_factory=dict)
    artifacts: list[str] = Field(default_factory=list)
    timed_out: bool = False


class VerdictStatus(str, Enum):
    reproduced = "reproduced"
    partial = "partial"
    failed = "failed"
    unverifiable = "unverifiable"


class Verdict(BaseModel):
    claim_id: str
    status: VerdictStatus
    paper_value: float
    measured_value: float | None = None
    delta: float | None = None
    evidence: str = ""
    diagnosis: str = ""


class Route(str, Enum):
    coder = "coder"
    methods_extractor = "methods_extractor"
    data_finder = "data_finder"
    reporter = "reporter"


class Diagnosis(BaseModel):
    """LLM output of the Critic: why did it fail, and where to go next."""
    route: Route
    explanation: str


class Budget(BaseModel):
    max_iterations: int = 4
    max_tokens: int = 400_000
    max_seconds: int = 3600
    exec_timeout_s: int = 600
    exec_memory_mb: int = 4096
    max_data_mb: int = 2000  # total across all datasets in one run
    install_timeout_s: int = 600


class RunState(BaseModel):
    run_id: str = Field(default_factory=lambda: time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6])
    url: str
    dry_run: bool = False
    budget: Budget = Field(default_factory=Budget)
    paper: Paper | None = None
    spec: ReproSpec | None = None
    datasets: list[DatasetRef] = Field(default_factory=list)
    attempt: int = 0
    exec_result: ExecResult | None = None
    verdicts: list[Verdict] = Field(default_factory=list)
    critic_feedback: str = ""
    route: Route | None = None
    route_history: list[Route] = Field(default_factory=list)  # every Critic reroute, in order
    tokens_used: int = 0
    started_at: float = Field(default_factory=time.time)
    status: Literal["running", "done", "budget_exhausted", "error"] = "running"
    error: str = ""

    def run_dir(self, root: Path) -> Path:
        return root / self.run_id

    def save(self, root: Path) -> None:
        d = self.run_dir(root)
        d.mkdir(parents=True, exist_ok=True)
        (d / "state.json").write_text(self.model_dump_json(indent=2))

    @classmethod
    def load(cls, path: Path) -> "RunState":
        return cls.model_validate(json.loads(path.read_text()))
