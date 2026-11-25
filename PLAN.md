# Build Plan

## Phase 0: scaffold (done in first session)
- [x] Docs, agent specs
- [x] Package skeleton, state models, orchestrator loop, tracing, CLI
- [x] Executor sandbox (subprocess)
- [x] LLM provider wired with a real key (OpenAI Responses API; Anthropic kept as an option)

## Phase 1: one paper end to end
Target: Deep Ensembles, arXiv:1612.01474 (UCI regression, Table 1). See `benchmark/papers.yaml`.

- [x] Ingestor: arXiv/bioRxiv fetch + PDF parse (pymupdf). bioRxiv falls back to Europe PMC JATS, then the abstract only (flagged). Section text is sliced verbatim by code; the LLM only marks headings.
- [x] Methods Extractor producing a valid ReproSpec (live; the prompt was fixed after run 1 so the spec is executable)
- [x] Data Finder: HEAD/size verification, downloads for GEO, PhysioNet, Zenodo and plain URLs. Unreachable data is marked missing. (GEO is tested only against mocks: NCBI rate-limited this IP during development.)
- [x] Coder + Executor + Critic retry loop (per-run venv with an install timeout, process-group kill, stale-metrics guards, a routing test per failure type)
- [x] Reporter (deterministic; supplementary metrics listed separately from verdicts)
- [ ] Reproduce at least one claim with the paper's stated protocol. Run 2: 0/5 reproduced at the stated Adam lr=0.1 (training unstable). An lr=0.01 sensitivity pass lands inside the paper's ± for 5/6 values, but that is a post-hoc deviation, not a reproduction.

### Phase 1 open issues
- Network is not restricted while `main.py` runs (ARCHITECTURE says allowlist only). API keys are scrubbed from its environment.
- `RLIMIT_AS` is not enforced on macOS, so the memory limit is best effort there.
- ~~Install-failure reroutes count toward `max_iterations`~~: now capped separately (MAX_INSTALL_RETRIES).
- ~~The Critic re-routes to methods_extractor repeatedly~~: a second re-read now goes to the reporter.

## Phase 2: benchmark
- [ ] 10 papers in benchmark/papers.yaml with ground-truth claims
- [ ] Scoring script, reproduction rate table
- [ ] Baseline: single-agent vs multi-agent comparison (the resume number)

## Phase 3: polish
- [x] Web app (static, from state.json + trace.jsonl): the lab dashboard, per-run page, claims wall, crew. `paperrepro site`
- [ ] Docker sandbox (also solves network restriction and memory limits on macOS)
- [ ] Demo GIF, README results table
- [ ] Optional: web UI, MCP server wrapper

## Small fixes
For any agent; see AGENTS.md. Each is one file or less.
- [x] `pyproject.toml`: add `filterwarnings = ["ignore::DeprecationWarning:importlib._bootstrap"]` under pytest options (the pymupdf SWIG warnings clutter `pytest -q`).
- [x] `cli.py`: annotate `provider` as `str | None` (it currently says `str` with a `None` default).
- [x] `tests/test_routing.py`: rename `agents_in_trace` to `trace_events` (it returns events, not agent names).
- [ ] `dryrun.py`: wrap the lines over 100 chars (they pass only because E501 is ignored).
- [x] `README.md`: update "Status" (it still says "Early scaffold") and document `.env` plus `--provider`.
- [x] `AGENTS.md`: setup line should be `uv pip install -e ".[dev,pdf,openai]"`.

## Dev workflow
- Claude Code: architecture, agents, orchestrator, anything multi-file.
- Freebuff / free agents: small bugs, lint fixes, tests, docs typos. They follow AGENTS.md.
- Keep commits small. Run `pytest` before every commit.
