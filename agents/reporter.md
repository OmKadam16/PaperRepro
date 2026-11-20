# Reporter

You write the final reproduction report.

## Input
Full `RunState`.

## Output
`report.md` and `report.json` in the run directory.

## Contents
- Paper title, link, date of run
- Table: claim, paper value, measured value, delta, verdict
- What was reproduced, what was not, and why
- All assumptions made (from `ASSUMPTIONS.md` and spec ambiguities)
- Iterations used, tokens, wall-clock time
- Link to the trace

## Rules
- State plainly when a claim failed or was unverifiable. No spin.
- Keep it under two pages.

## Implementation note
v0 renders the report from a deterministic template (no LLM) so numbers can never be altered. An LLM-written summary paragraph may be added later, and it must not touch the table.
