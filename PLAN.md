# Build Plan

## Phase 0: scaffold (done in first session)
- [x] Docs, agent specs
- [x] Package skeleton, state models, orchestrator loop, tracing, CLI
- [x] Executor sandbox (subprocess)
- [ ] LLM provider wired with a real key

## Phase 1: one paper end to end
- [ ] Ingestor: arXiv/bioRxiv fetch + PDF parse (pymupdf)
- [ ] Methods Extractor producing a valid ReproSpec
- [ ] Data Finder for GEO + PhysioNet
- [ ] Coder + Executor + Critic retry loop
- [ ] Reporter
- Target paper: a small, well-documented, fast-to-run one (pick from benchmark/papers.yaml)

## Phase 2: benchmark
- [ ] 10 papers in benchmark/papers.yaml with ground-truth claims
- [ ] Scoring script, reproduction rate table
- [ ] Baseline: single-agent vs multi-agent comparison (the resume number)

## Phase 3: polish
- [ ] Trace viewer (static HTML from trace.jsonl)
- [ ] Docker sandbox
- [ ] Demo GIF, README results table
- [ ] Optional: web UI, MCP server wrapper

## Dev workflow
- Claude Code: architecture, agents, orchestrator, anything multi-file.
- Freebuff / free agents: small bugs, lint fixes, tests, docs typos. They follow AGENTS.md.
- Keep commits small. Run `pytest` before every commit.
