"""Run a workspace in a subprocess with time and memory limits (v1 sandbox)."""
from __future__ import annotations

import json
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
        except Exception:
            pass

    return apply


def run_workspace(
    workspace: Path, *, timeout_s: int, mem_mb: int, install_deps: bool = True
) -> ExecResult:
    t0 = time.time()
    py = sys.executable
    if install_deps and (workspace / "requirements.txt").exists():
        venv = workspace / ".venv"
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True, capture_output=True)
        py = str(venv / "bin" / "python")
        pip = subprocess.run(
            [py, "-m", "pip", "install", "-q", "-r", "requirements.txt"],
            cwd=workspace, capture_output=True, text=True, timeout=timeout_s,
        )
        if pip.returncode != 0:
            return ExecResult(
                exit_code=pip.returncode, stderr_tail=pip.stderr[-TAIL:],
                duration_s=time.time() - t0,
            )
    try:
        p = subprocess.run(
            [py, "main.py"], cwd=workspace, capture_output=True, text=True,
            timeout=timeout_s, preexec_fn=_limits(mem_mb),
        )
        code, out, err, timed_out = p.returncode, p.stdout, p.stderr, False
    except subprocess.TimeoutExpired as e:
        code, out, err, timed_out = -1, (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or ""), "timeout", True

    metrics: dict[str, float] = {}
    mpath = workspace / "results" / "metrics.json"
    if mpath.exists():
        try:
            raw = json.loads(mpath.read_text())
            metrics = {k: float(v) for k, v in raw.items()}
        except Exception as ex:  # malformed metrics counts as no metrics
            err += f"\nmetrics.json unreadable: {ex}"
    results_dir = workspace / "results"
    artifacts = sorted(str(p.relative_to(workspace)) for p in results_dir.rglob("*") if p.is_file()) if results_dir.exists() else []
    return ExecResult(
        exit_code=code, stdout_tail=out[-TAIL:], stderr_tail=err[-TAIL:],
        duration_s=round(time.time() - t0, 2), metrics=metrics, artifacts=artifacts,
        timed_out=timed_out,
    )
