from __future__ import annotations

from pathlib import Path

import typer
from rich import print

app = typer.Typer(no_args_is_help=True, help="Find the published sources behind every claim in your draft.")


@app.command()
def serve(
    port: int = typer.Option(8765, help="Port on 127.0.0.1"),
    projects_dir: Path = typer.Option(Path("projects"), help="Where drafts and results are kept"),
) -> None:
    """Start the web app, then open http://127.0.0.1:8765"""
    from paperrepro.server import serve as _serve

    _serve(projects_dir, port=port)


@app.command()
def cite(
    path: Path = typer.Argument(..., help="Your draft: .pdf, .docx, .txt or .md"),
    projects_dir: Path = typer.Option(Path("projects"), help="Where drafts and results are kept"),
) -> None:
    """Process one draft from the command line and print what was found."""
    from paperrepro.env import load_dotenv
    from paperrepro.llm import make_llm
    from paperrepro.pipeline import process
    from paperrepro.state import Project

    load_dotenv()
    p = process(Project(filename=path.name), path.read_bytes(), make_llm(), projects_dir)
    print(f"[bold]{p.status}[/bold]  {p.progress}  ({p.tokens_used} tokens)")
    if p.error:
        print(f"[red]{p.error}[/red]")
    for c in p.claims:
        s = p.draft.sentence(c.sentence_id)
        print(f"\n[cyan]{c.sentence_id}[/cyan] {s.text if s else ''}")
        for m in (m for m in p.matches if m.sentence_id == c.sentence_id):
            src = p.sources[m.source_id]
            print(f"   {m.verdict:8} {src.title[:90]} ({src.year})  {src.url}")
    print(f"\nopen it in the app: paperrepro serve, then http://127.0.0.1:8765/d/{p.id}")


if __name__ == "__main__":
    app()
