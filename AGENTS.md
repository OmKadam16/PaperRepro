# AGENTS.md (for small fixes by any coding agent)

PaperRepro: multi-agent system that reproduces paper results. Python 3.10+.

## Setup
```
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
pytest -q
```

## Do
- Fix bugs, lint errors, typos, add or fix unit tests, small refactors inside one file.
- Keep changes minimal and run `pytest -q` and `ruff check .` after.

## Do not
- Do not change `agents/*.md` prompts or `ARCHITECTURE.md` without being asked.
- Do not change the models in `src/paperrepro/state.py` without being asked (other modules depend on them).
- Do not commit anything under `runs/`, `.env`, or API keys.
- Do not add dependencies without asking.

## Layout
See ARCHITECTURE.md "Repo layout".
