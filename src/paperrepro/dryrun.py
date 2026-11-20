"""Fake LLM for testing the plumbing with no API key. Outputs are synthetic, never real results."""
from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

from paperrepro.llm import Usage
from paperrepro.state import (
    Claim,
    CodeBundle,
    DatasetList,
    DatasetRef,
    Diagnosis,
    Paper,
    ReproSpec,
    Route,
    Section,
)

T = TypeVar("T", bound=BaseModel)

_CRASH = "raise RuntimeError('synthetic crash (dry run)')\n"
_OK = (
    "import json, pathlib\n"
    "pathlib.Path('results').mkdir(exist_ok=True)\n"
    "json.dump({'c1': 0.91}, open('results/metrics.json', 'w'))\n"
)


class DryRunLLM:
    """First coder attempt crashes on purpose so the retry loop is exercised."""

    def __init__(self) -> None:
        self.coder_calls = 0

    def structured(self, *, agent: str, system: str, prompt: str, schema: type[T]) -> tuple[T, Usage]:
        u = Usage(10, 10)
        if schema is Paper:
            return Paper(title="[DRY RUN] Example paper", sections=[Section(heading="Methods", text="...")]), u  # type: ignore[return-value]
        if schema is ReproSpec:
            return ReproSpec(  # type: ignore[return-value]
                claims=[Claim(id="c1", description="synthetic accuracy", metric="accuracy",
                              paper_value=0.90, tolerance=0.05)],
                datasets=["synthetic"], ambiguities=["dry run: all values synthetic"],
            ), u
        if schema is DatasetList:
            return DatasetList(items=[DatasetRef(name="synthetic", source="other")]), u  # type: ignore[return-value]
        if schema is CodeBundle:
            self.coder_calls += 1
            return CodeBundle(files={"main.py": _CRASH if self.coder_calls == 1 else _OK}), u  # type: ignore[return-value]
        if schema is Diagnosis:
            return Diagnosis(route=Route.coder, explanation="main.py crashed; fix the code."), u  # type: ignore[return-value]
        raise NotImplementedError(schema)
