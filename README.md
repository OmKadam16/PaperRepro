# PaperRepro

A multi-agent system that **reproduces a paper's results**. Give it a bioRxiv / arXiv link; it reads the methods, finds the dataset, writes the analysis code, runs it in a sandbox, and checks its numbers against the paper's.

```
paperrepro run https://www.biorxiv.org/content/...   # one paper
paperrepro bench benchmark/papers.yaml               # eval harness
```

## Why
Reproducibility is the bottleneck in computational science. PaperRepro turns "can I trust this result?" into a measurable, automated pipeline, with a score for every paper.

## How it works
Orchestrator-driven pipeline of specialist agents with a verify-and-retry loop:

`Ingestor -> Methods Extractor -> Data Finder -> Coder <-> Executor -> Critic -> Reporter`

The Critic compares reproduced numbers to the paper's claims and routes failures back to the right agent. See [ARCHITECTURE.md](ARCHITECTURE.md).

## Status
Early scaffold. See [PLAN.md](PLAN.md) for the build roadmap.

## Eval
Every run produces a verdict per claim (`reproduced`, `partial`, `failed`, `unverifiable`). The benchmark reports the reproduction rate across a fixed paper set. That number is the headline metric.
