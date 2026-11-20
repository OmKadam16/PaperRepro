# CLAUDE.md

Project: PaperRepro, a multi-agent paper reproduction system. Read ARCHITECTURE.md first.

## Rules
- Agent specs live in `agents/*.md` and are loaded as system prompts. Change behavior there, not by hardcoding prompts in Python.
- All inter-agent data goes through typed models in `src/paperrepro/state.py`. No ad-hoc dicts.
- Measured values come only from Executor output. Never write paper numbers into results.
- Every agent call must be traced via `trace.py`.
- Keep modules small; one agent per file.
- Run `pytest` and `ruff check .` before finishing a task.

## Commands
- `uv pip install -e ".[dev]"` to install
- `pytest -q`
- `paperrepro run <url> --dry-run` to exercise the pipeline without an LLM key

## Division of labor
Claude Code owns architecture, agent logic, orchestration. Small fixes (typos, lint, simple tests) may be done by other agents; see AGENTS.md.
