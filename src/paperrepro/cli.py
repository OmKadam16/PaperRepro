from __future__ import annotations

from pathlib import Path

import typer
from rich import print

from paperrepro.orchestrator import run_pipeline
from paperrepro.state import Budget, RunState

app = typer.Typer(no_args_is_help=True, help="Reproduce a paper's results with a team of agents.")


@app.command()
def run(
    url: str = typer.Argument(..., help="Paper URL (arXiv / bioRxiv / PDF)"),
    dry_run: bool = typer.Option(False, help="Synthetic agents, no API key; tests the plumbing"),
    runs_dir: Path = typer.Option(Path("runs"), help="Where run output goes"),
    max_iterations: int = typer.Option(4, help="Max critic -> reroute cycles"),
    provider: str | None = typer.Option(None, help="openai | anthropic (default: whichever key is set)"),
) -> None:
    if dry_run:
        from paperrepro.dryrun import DryRunLLM
        llm = DryRunLLM()
    else:
        from paperrepro.env import load_dotenv
        from paperrepro.llm import make_llm
        loaded = load_dotenv()
        if loaded:
            print(f"loaded from .env: {', '.join(loaded)}")
        llm = make_llm(provider)
    state = RunState(url=url, dry_run=dry_run, budget=Budget(max_iterations=max_iterations))
    state = run_pipeline(state, llm, runs_dir)
    print(f"[bold]status:[/bold] {state.status}  run: {state.run_id}")
    for v in state.verdicts:
        print(f"  {v.claim_id}: {v.status.value} (paper {v.paper_value}, measured {v.measured_value})")
    print(f"report: {state.run_dir(runs_dir) / 'report.md'}")


@app.command()
def report(run_dir: Path = typer.Argument(..., help="runs/<id> directory")) -> None:
    """Re-render report.md/json from a run's saved state.json (deterministic, no LLM)."""
    from paperrepro.agents import reporter
    from paperrepro.trace import Tracer

    state = RunState.load(run_dir / "state.json")
    reporter.run(state, Tracer(run_dir / "trace.jsonl"), run_dir.parent)
    print(f"report: {run_dir / 'report.md'}")


@app.command()
def view(run_dir: Path = typer.Argument(..., help="runs/<id> directory")) -> None:
    """Write runs/<id>/view.html, a self-contained visual of the run (open it in a browser)."""
    from paperrepro.viewer import write

    print(f"view: {write(run_dir)}")


@app.command()
def bench(path: Path) -> None:
    """Run the benchmark set (planned: Phase 2)."""
    print("[yellow]bench is not implemented yet (see PLAN.md Phase 2)[/yellow]")
    raise typer.Exit(1)


if __name__ == "__main__":
    app()
