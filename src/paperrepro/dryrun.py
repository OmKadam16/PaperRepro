"""Fake LLM for testing the plumbing with no API key. Outputs are synthetic, never real results.

Scenarios script one failure on the first attempt, so each Critic route is exercised:
  crash         main.py raises            -> Critic routes to coder
  wrong_metric  runs, value off           -> Critic routes to methods_extractor
  bad_data      data file not found       -> Critic routes to data_finder
"""
from __future__ import annotations

from collections import Counter
from typing import Literal, TypeVar

from pydantic import BaseModel

from paperrepro.llm import Usage
from paperrepro.state import (
    Claim,
    CodeBundle,
    DatasetList,
    Diagnosis,
    Paper,
    ReproSpec,
    Route,
    Section,
)

T = TypeVar("T", bound=BaseModel)
Scenario = Literal["crash", "wrong_metric", "bad_data"]


def _metric(v: float) -> str:
    return (
        "import json, pathlib\n"
        "pathlib.Path('results').mkdir(exist_ok=True)\n"
        f"json.dump({{'c1': {v}}}, open('results/metrics.json', 'w'))\n"
    )


FIRST_ATTEMPT = {
    "crash": "raise RuntimeError('synthetic crash (dry run)')\n",
    "wrong_metric": _metric(0.5),
    "bad_data": "open('data/synthetic/train.csv').read()\n",
}
DIAGNOSIS = {
    "crash": Diagnosis(route=Route.coder, explanation="main.py crashed; fix the code."),
    "wrong_metric": Diagnosis(route=Route.methods_extractor,
                              explanation="code is faithful to the spec but the metric is off; "
                                          "re-read the paper for a missed preprocessing step."),
    "bad_data": Diagnosis(route=Route.data_finder,
                          explanation="FileNotFoundError on data/synthetic/train.csv; find the data."),
}


class DryRunLLM:
    """First coder attempt fails per `scenario`; later attempts succeed."""

    def __init__(self, scenario: Scenario = "crash") -> None:
        self.scenario = scenario
        self.calls: Counter[str] = Counter()

    @property
    def coder_calls(self) -> int:
        return self.calls["coder"]

    def structured(self, *, agent: str, system: str, prompt: str, schema: type[T]) -> tuple[T, Usage]:
        self.calls[agent] += 1
        self.last_prompt = prompt
        u = Usage(10, 10, "dry-run")
        if schema is Paper:
            return Paper(title="[DRY RUN] Example paper", sections=[Section(heading="Methods", text="...")]), u  # type: ignore[return-value]
        if schema is ReproSpec:
            return ReproSpec(  # type: ignore[return-value]
                claims=[Claim(id="c1", description="synthetic accuracy", metric="accuracy",
                              paper_value=0.90, tolerance=0.05)],
                datasets=[], ambiguities=["dry run: all values synthetic"],
            ), u
        if schema is DatasetList:
            return DatasetList(items=[]), u  # type: ignore[return-value]
        if schema is CodeBundle:
            first = self.calls["coder"] == 1
            return CodeBundle(files={"main.py": FIRST_ATTEMPT[self.scenario] if first else _metric(0.91)}), u  # type: ignore[return-value]
        if schema is Diagnosis:
            return DIAGNOSIS[self.scenario], u  # type: ignore[return-value]
        raise NotImplementedError(schema)
