# PaperRepro

A multi-agent system that **reproduces a paper's results**. Give it a bioRxiv / arXiv link; it reads the methods, finds the dataset, writes the analysis code, runs it in a sandbox, and checks its numbers against the paper's.

```
uv pip install -e ".[dev,pdf,openai]"
echo 'OPENAI_API_KEY=sk-...' > .env                  # gitignored; or ANTHROPIC_API_KEY
paperrepro run https://arxiv.org/abs/1612.01474      # one paper (also rebuilds the web app)
paperrepro site                                      # web app -> runs/_site/index.html
paperrepro report runs/<id>                          # re-render report.md from state.json
paperrepro run <url> --dry-run                       # plumbing only, no API key
```

Models are set per agent in `src/paperrepro/llm.py` and can be overridden with
`PAPERREPRO_MODEL_<AGENT>=...` (or `PAPERREPRO_MODEL` for all agents) in `.env`.

## Web app
`runs/_site/` is a static, offline site built from each run's `state.json` and `trace.jsonl`:
- **the lab**: headline result, a punch card of every claim, reroute tallies, tokens per run, run ledger
- **a run**: verdict stamp, the run's path with every reroute, a ruler per claim, the judge's notes, data, assumptions
- **claims**: every claim from every finished run, filterable by verdict and sortable by distance from the paper
- **crew**: each agent, its model, its calls and tokens, and its full instructions

## Why
Reproducibility is the bottleneck in computational science. PaperRepro turns "can I trust this result?" into a measurable, automated pipeline, with a score for every paper.

## How it works
Orchestrator-driven pipeline of specialist agents with a verify-and-retry loop:

`Ingestor -> Methods Extractor -> Data Finder -> Coder <-> Executor -> Critic -> Reporter`

The Critic compares reproduced numbers to the paper's claims and routes failures back to the right agent. See [ARCHITECTURE.md](ARCHITECTURE.md).

## Status
Phase 1: runs end to end on one paper (Deep Ensembles, arXiv:1612.01474). See [PLAN.md](PLAN.md).

## Eval
Every run produces a verdict per claim (`reproduced`, `partial`, `failed`, `unverifiable`). The benchmark reports the reproduction rate across a fixed paper set. That number is the headline metric.
