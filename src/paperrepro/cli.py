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
    request: str = typer.Option("", help="What to check, in plain words (e.g. 'only Table 1 RMSE')"),
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
    state = RunState(url=url, user_request=request, dry_run=dry_run,
                     budget=Budget(max_iterations=max_iterations))
    state = run_pipeline(state, llm, runs_dir)
    print(f"[bold]status:[/bold] {state.status}  run: {state.run_id}")
    for v in state.verdicts:
        print(f"  {v.claim_id}: {v.status.value} (paper {v.paper_value}, measured {v.measured_value})")
    print(f"report: {state.run_dir(runs_dir) / 'report.md'}")
    from paperrepro.site import build_site

    build_site(runs_dir)
    print(f"web app: {runs_dir / '_site' / ('run-' + state.run_id + '.html')}")


@app.command()
def report(run_dir: Path = typer.Argument(..., help="runs/<id> directory")) -> None:
    """Re-render report.md/json from a run's saved state.json (deterministic, no LLM)."""
    from paperrepro.agents import reporter
    from paperrepro.trace import Tracer

    state = RunState.load(run_dir / "state.json")
    reporter.run(state, Tracer(run_dir / "trace.jsonl"), run_dir.parent)
    print(f"report: {run_dir / 'report.md'}")


@app.command()
def site(runs_dir: Path = typer.Option(Path("runs"), help="Where run output lives")) -> None:
    """Build the web app (the lab, claims, crew, one page per run) into runs/_site/."""
    from paperrepro.site import build_site

    print(f"open: {build_site(runs_dir)}")


@app.command()
def view(run_dir: Path = typer.Argument(..., help="runs/<id> directory")) -> None:
    """Rebuild the web app and print the page for one run."""
    from paperrepro.site import build_site

    build_site(run_dir.parent)
    print(f"open: {run_dir.parent / '_site' / ('run-' + run_dir.name + '.html')}")


@app.command()
def serve(
    port: int = typer.Option(8765, help="Port on 127.0.0.1"),
    runs_dir: Path = typer.Option(Path("runs"), help="Where run output goes"),
    dry_run: bool = typer.Option(False, help="Synthetic agents, no API key (try the UI for free)"),
) -> None:
    """Start the web app: submit papers in the browser and watch the agents work."""
    from paperrepro.server import serve as _serve

    _serve(runs_dir, port=port, dry_run=dry_run)


@app.command()
def bench(path: Path) -> None:
    """Run the benchmark set (planned: Phase 2)."""
    print("[yellow]bench is not implemented yet (see PLAN.md Phase 2)[/yellow]")
    raise typer.Exit(1)


if __name__ == "__main__":
    app()
