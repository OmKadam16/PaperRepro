"""Run a workspace in a subprocess with time and memory limits (v1 sandbox).

Phases: (1) per-run venv + dependency install, with its own timeout and a cache keyed on
requirements.txt; (2) `python main.py` in its own process group, killed as a group on timeout.
results/ is wiped before every run and metrics.json is only read if this run wrote it.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from paperrepro.state import ExecResult

TAIL = 4000


def _limits(mem_mb: int):
    def apply() -> None:
        try:
            import resource

            b = mem_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (b, b))
        except Exception:  # not enforceable on every OS (e.g. macOS); best effort
            pass

    return apply


def _tail(p: Path) -> str:
    if not p.exists():
        return ""
    with p.open("rb") as f:
        f.seek(max(0, p.stat().st_size - TAIL))
        return f.read().decode(errors="replace")


def _run_logged(cmd: list[str], cwd: Path, log_dir: Path, name: str, timeout_s: int,
                env: dict[str, str], preexec=None) -> tuple[int, bool]:
    """Run cmd, streaming output to files (no unbounded memory). Returns (exit_code, timed_out)."""
    log_dir.mkdir(parents=True, exist_ok=True)
    with (log_dir / f"{name}.stdout").open("wb") as out, (log_dir / f"{name}.stderr").open("wb") as err:
        p = subprocess.Popen(cmd, cwd=cwd, stdout=out, stderr=err, env=env,
                             start_new_session=True, preexec_fn=preexec)
        try:
            return p.wait(timeout=timeout_s), False
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, signal.SIGKILL)  # kill the whole group, incl. grandchildren
            p.wait()
            return -1, True


def ensure_venv(workspace: Path, log_dir: Path, timeout_s: int, env: dict[str, str]) -> tuple[str, str]:
    """Create/reuse workspace/.venv and install requirements.txt. Returns (python, error)."""
    venv = workspace / ".venv"
    py = venv / "bin" / "python"
    req = workspace / "requirements.txt"
    digest = hashlib.sha256(req.read_bytes()).hexdigest()
    stamp = venv / ".requirements.sha256"
    if py.exists() and stamp.exists() and stamp.read_text() == digest:
        return str(py), ""
    shutil.rmtree(venv, ignore_errors=True)
    uv = shutil.which("uv")
    steps = ([[uv, "venv", "-q", "--python", sys.executable, str(venv)],
              [uv, "pip", "install", "-q", "--python", str(py), "-r", str(req)]] if uv else
             [[sys.executable, "-m", "venv", str(venv)],
              [str(py), "-m", "pip", "install", "-q", "-r", str(req)]])
    deadline = time.time() + timeout_s
    for i, cmd in enumerate(steps):
        left = max(1, int(deadline - time.time()))
        code, timed_out = _run_logged(cmd, workspace, log_dir, f"install{i}", left, env)
        if timed_out:
            return "", f"[install] dependency install timed out after {timeout_s}s"
        if code != 0:
            return "", f"[install] `{' '.join(cmd[:4])} ...` failed (exit {code}):\n" + _tail(
                log_dir / f"install{i}.stderr")
    stamp.write_text(digest)
    return str(py), ""


def read_metrics(path: Path, not_before: float) -> tuple[dict[str, float], str]:
    """Numeric metrics written by this run only. Returns (metrics, problems)."""
    if not path.exists():
        return {}, ""
    if path.stat().st_mtime < not_before:
        return {}, "metrics.json predates this run; ignored as stale"
    try:
        raw = json.loads(path.read_text())
    except Exception as ex:
        return {}, f"metrics.json unreadable: {ex}"
    if not isinstance(raw, dict):
        return {}, "metrics.json is not a JSON object"
    out, bad = {}, []
    for k, v in raw.items():
        if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v):
            out[str(k)] = float(v)
        else:
            bad.append(k)
    return out, (f"metrics.json: non-numeric or non-finite values ignored for {bad}" if bad else "")


def run_workspace(
    workspace: Path, *, timeout_s: int, mem_mb: int, install_deps: bool = True,
    install_timeout_s: int = 600,
) -> ExecResult:
    t0 = time.time()
    log_dir = workspace / "logs"
    shutil.rmtree(log_dir, ignore_errors=True)
    env = {**os.environ, "PYTHONHASHSEED": "0", "MPLBACKEND": "Agg", "PYTHONUNBUFFERED": "1"}
    env.pop("VIRTUAL_ENV", None)
    py = sys.executable
    if install_deps and (workspace / "requirements.txt").exists():
        py, err = ensure_venv(workspace, log_dir, install_timeout_s, env)
        if err:
            return ExecResult(exit_code=-1, stderr_tail=err[-TAIL:], duration_s=round(time.time() - t0, 2),
                              timed_out="timed out" in err)

    results = workspace / "results"
    shutil.rmtree(results, ignore_errors=True)  # nothing from a previous attempt survives
    results.mkdir(parents=True)
    run_start = time.time() - 1  # mtime granularity slack
    code, timed_out = _run_logged([py, "main.py"], workspace, log_dir, "run", timeout_s, env,
                                  preexec=_limits(mem_mb))
    out, err = _tail(log_dir / "run.stdout"), _tail(log_dir / "run.stderr")
    if timed_out:
        err += f"\n[run] killed after {timeout_s}s timeout"
    metrics, problem = read_metrics(results / "metrics.json", run_start)
    if problem:
        err += f"\n{problem}"
    artifacts = sorted(str(p.relative_to(workspace)) for p in results.rglob("*") if p.is_file())
    return ExecResult(
        exit_code=code, stdout_tail=out[-TAIL:], stderr_tail=err[-TAIL:],
        duration_s=round(time.time() - t0, 2), metrics=metrics, artifacts=artifacts,
        timed_out=timed_out,
    )
