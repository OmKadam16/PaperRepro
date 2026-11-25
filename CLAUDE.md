# CLAUDE.md

Project: PaperRepro, a research workbench in five stages: find a gap, plan, figures, cite, review. Read ARCHITECTURE.md first.

(The earlier paper-reproduction pipeline lives at git tag `reproduction-v1`.)

## Rules
- Helper specs live in `agents/*.md` and are loaded as system prompts. Change behavior there, not by hardcoding prompts in Python.
- All inter-agent data goes through typed models in `src/paperrepro/state.py`. No ad-hoc dicts.
- Sources come only from scholarly database records (`tools/literature.py`). An LLM may judge a source, never create one, edit its metadata, or invent a quote.
- Citation text and reference lists are produced by deterministic code (`cite.py`), never by an LLM.
- Every LLM call must be traced via `trace.py`.
- Keep modules small; one helper per file.
- Run `pytest` and `ruff check .` before finishing a task.

## Commands
- `uv pip install -e ".[dev,pdf,openai]"` to install
- `pytest -q`
- `paperrepro serve` then open http://127.0.0.1:8765
- `paperrepro cite draft.pdf` to process one file from the terminal

## Division of labor
Claude Code owns architecture, helper logic, the pipeline and the UI. Small fixes (typos, lint, simple tests) may be done by other agents; see AGENTS.md.
