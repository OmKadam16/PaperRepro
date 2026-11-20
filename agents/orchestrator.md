# Orchestrator

**Role:** Controls the run. Decides which agent runs next, enforces budgets, and decides when to stop.
**Type:** Deterministic state machine (code), with an optional LLM call only for ambiguous routing.

## Inputs
`RunState` (full).

## Outputs
Next step name, or `done`.

## Rules
- Follow the routing table in ARCHITECTURE.md.
- Stop when: all claims have a final verdict, or the iteration, token, or time budget is exhausted.
- Persist `RunState` and append a trace event after every step.
- Never edit another agent's output; only route.
