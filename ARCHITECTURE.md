# Architecture

## Goals
1. Reproduce quantitative claims from a paper end to end, with no human in the loop.
2. Be honest: report `unverifiable` rather than faking a match.
3. Be observable: every agent handoff is traced and replayable.
4. Be measurable: a fixed benchmark gives a reproduction rate.

## Pipeline

```
          +-----------------------------------------------+
          |                  Orchestrator                 |
          |  state machine, budget, routing, retries      |
          +----+--------+---------+--------+--------+-----+
               |        |         |        |        |
          Ingestor  Methods    Data     Coder <-> Executor
                    Extractor  Finder       |
                                          Critic ---> Reporter
```

Flow:
1. **Ingestor**: fetch paper (PDF/HTML), parse to structured text + tables + figure captions.
2. **Methods Extractor**: produce a `ReproSpec`: target claims (metric, value, tolerance), datasets, preprocessing, models, hyperparameters, software versions. Flags ambiguity explicitly.
3. **Data Finder**: resolve datasets to concrete downloadable sources (GEO, PhysioNet, Zenodo, HF, GitHub). Verifies availability and size before download.
4. **Coder**: writes the analysis code against the `ReproSpec` and the dataset manifest. Outputs a runnable project in `runs/<id>/workspace/`.
5. **Executor** (not an LLM): runs code in a sandbox with time/memory limits, captures stdout, stderr, artifacts, metrics JSON.
6. **Critic**: compares measured metrics to claims. Verdict per claim. On failure, diagnoses the cause and **routes back** (fix code, re-find data, or re-read methods).
7. **Reporter**: writes the final reproduction report (markdown + JSON).

## State
One `RunState` (pydantic) persisted to `runs/<id>/state.json` after every step. Resumable. Agents read and write typed fields, never free-form shared memory.

Key models (`src/paperrepro/state.py`): `Paper`, `Claim`, `ReproSpec`, `DatasetRef`, `ExecResult`, `Verdict`, `RunState`.

## Routing rules (Critic -> next step)
| Diagnosis | Route to |
|---|---|
| Code error / crash | Coder |
| Metric off, code looks faithful | Methods Extractor (re-read for missed detail) |
| Data missing / wrong split | Data Finder |
| Metric within tolerance | Reporter |
| Retry budget exhausted | Reporter with `failed` / `partial` |

Global budget: max iterations, max tokens, max wall-clock. Orchestrator enforces.

## Tracing
`runs/<id>/trace.jsonl`: one event per agent call (agent, input hash, output summary, tokens, duration, route taken). A trace viewer (later) renders the handoff graph.

## LLM layer
`llm.py` exposes one interface (`complete(system, messages, schema=None)`). Default provider: Anthropic. Swappable, so cheap models can handle cheap agents (Ingestor, Reporter) and strong models handle Coder/Critic.

## Sandbox
v1: subprocess with `resource` limits, per-run venv, no network except an allowlist during the data-fetch step. v2: Docker.

## Honesty rules
- Never copy numbers from the paper into the result.
- Executor outputs are the only source of measured values.
- Critic must cite the artifact path for each measured number.
- Unreachable data or missing method details -> `unverifiable`, with the reason.

## Repo layout
```
agents/        agent specs (.md) = system prompts, single source of truth
src/paperrepro/
  orchestrator.py  state.py  llm.py  trace.py  cli.py
  agents/        one module per agent
  tools/         pdf, fetch, sandbox
benchmark/       papers.yaml + scoring
runs/            per-run output (gitignored)
tests/
```
