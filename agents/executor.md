# Executor

**Type:** Deterministic tool (no LLM).

## Job
Run the Coder's workspace in a sandbox and return an `ExecResult`.

## Behavior
- Create a per-run virtualenv, install `requirements.txt`.
- Run `main.py` with wall-clock, memory, and output-size limits.
- Capture `stdout`, `stderr`, exit code, duration, and the contents of `results/metrics.json`.
- Network access only during dependency and data download steps.

## Output (`ExecResult`)
`exit_code`, `stdout_tail`, `stderr_tail`, `duration_s`, `metrics` (dict), `artifacts` (paths), `timed_out` (bool).
