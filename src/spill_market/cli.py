"""Human and automation entry point; no web server required for experiments."""
from __future__ import annotations

import asyncio
import json
import platform
import sqlite3
import sys
import threading
import webbrowser
from pathlib import Path
from typing import Annotated

import typer

from . import __version__
from .examples import examples as demo_examples
from .models import MediaPlan, ResearchRequest, StudySpec
from .storage import Store

app = typer.Typer(no_args_is_help=True, help="Spill the Market — a local product-launch laboratory.")
study_app = typer.Typer(help="Create and inspect local experiments.")
app.add_typer(study_app, name="study")


def emit(value):
    typer.echo(json.dumps(value, ensure_ascii=False, indent=2))


@app.command()
def examples():
    """Print fictional, editable StudySpec examples. Does not access the network."""
    emit(demo_examples())


@app.command()
def doctor():
    """Check runtime capabilities without starting services or making requests."""
    from .api import provider_status
    with sqlite3.connect(":memory:") as db:
        try:
            db.execute("CREATE VIRTUAL TABLE search USING fts5(text)")
            fts = True
        except sqlite3.OperationalError:
            fts = False
    emit({"version": __version__, "python": platform.python_version(), "platform": platform.platform(),
          "fts5": fts, "bundled_frontend": (Path(__file__).parent / "web" / "index.html").is_file(),
          "providers": provider_status(), "paid_requests_performed": 0})
    if not fts:
        raise typer.Exit(1)


@app.command()
def serve(
    host: str = "127.0.0.1", port: int = 8765,
    data_dir: Annotated[Path | None, typer.Option()] = None,
    open_browser: Annotated[bool, typer.Option("--open/--no-open")] = False,
    env_file: Annotated[Path | None, typer.Option(exists=True, dir_okay=False)] = None,
):
    """Serve the bundled local web app. Bind to loopback only."""
    import uvicorn
    from .api import create_app
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise typer.BadParameter("The local application only supports loopback hosts")
    if not 1 <= port <= 65535:
        raise typer.BadParameter("port must be between 1 and 65535")
    if env_file:
        from .settings import load_env_file
        load_env_file(env_file)
    if open_browser:
        browser_host = "[::1]" if host == "::1" else host
        threading.Timer(1.5, webbrowser.open, args=(f"http://{browser_host}:{port}",)).start()
    uvicorn.run(create_app(data_dir), host=host, port=port, access_log=False)


@study_app.command("create")
def create_study(
    spec_file: Annotated[Path | None, typer.Option("--spec", exists=True, dir_okay=False)] = None,
    example: str = "game",
    data_dir: Annotated[Path | None, typer.Option()] = None,
):
    """Prepare an offline study from JSON or a fictional example."""
    from .services import prepare_study
    if spec_file:
        spec = StudySpec.model_validate_json(spec_file.read_text(encoding="utf-8-sig"))
    else:
        sample = next((x for x in demo_examples() if x["id"] == example), None)
        if sample is None:
            raise typer.BadParameter("example must be game or software")
        spec = StudySpec.model_validate(sample["spec"])
    study = asyncio.run(prepare_study(Store(data_dir), spec))
    emit(study)


@study_app.command("list")
def list_studies(data_dir: Annotated[Path | None, typer.Option()] = None):
    emit(Store(data_dir).list_studies())


@study_app.command("show")
def show_study(study_id: str, data_dir: Annotated[Path | None, typer.Option()] = None):
    emit(Store(data_dir).get_study(study_id))


@app.command()
def simulate(
    study_id: str,
    plans_file: Annotated[Path | None, typer.Option("--plans", exists=True, dir_okay=False)] = None,
    data_dir: Annotated[Path | None, typer.Option()] = None,
    background: bool = False,
):
    """Compare three strategies using the exact same engine as the browser."""
    from .api import validate_plans
    from .jobs import reconcile_workers, spawn_worker
    from .worker import execute_run
    store = Store(data_dir)
    reconcile_workers(store, include_unstarted=True)
    study = store.get_study(study_id)
    spec = StudySpec.model_validate(study["spec"])
    raw = json.loads(plans_file.read_text(encoding="utf-8-sig")) if plans_file else study["plans"]
    if isinstance(raw, dict):
        raw = raw["plans"]
    plans = [MediaPlan.model_validate(p) for p in raw]
    validate_plans(spec, plans)
    run = store.create_run(study_id, spec.model_dump(), [p.model_dump() for p in plans])
    if background:
        spawn_worker(store, run["id"])
    else:
        execute_run(store.root, run["id"])
    emit(store.get_run(run["id"]))


@app.command()
def demo(
    example: str = "game", population: int = 1000, days: int = 30, repetitions: int = 10,
    data_dir: Annotated[Path | None, typer.Option()] = None,
    output: Annotated[Path | None, typer.Option()] = None,
):
    """Run a complete, explicitly fictional experiment without any API calls."""
    from .services import prepare_study
    from .worker import execute_run
    item = next((x for x in demo_examples() if x["id"] == example), None)
    if item is None:
        raise typer.BadParameter("example must be game or software")
    spec = StudySpec.model_validate(item["spec"])
    spec.audience.representatives = min(spec.audience.representatives, population)
    spec.audience.population = population
    spec.rounds = days
    spec.exploration_repetitions = repetitions
    spec.validation_repetitions = repetitions
    store = Store(data_dir)
    study = asyncio.run(prepare_study(store, spec))
    run = store.create_run(study["id"], spec.model_dump(), study["plans"])
    report = execute_run(store.root, run["id"])
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    emit({"run_id": run["id"], "status": store.get_run(run["id"])["status"],
          "winner_id": report.get("winner_id"), "output": str(output) if output else None,
          "api_cost_usd": 0, "population": population, "rounds": days})


@app.command()
def status(run_id: str, data_dir: Annotated[Path | None, typer.Option()] = None):
    from .jobs import reconcile_workers
    store = Store(data_dir)
    reconcile_workers(store)
    emit(store.get_run(run_id))


@app.command()
def cancel(run_id: str, data_dir: Annotated[Path | None, typer.Option()] = None):
    store = Store(data_dir)
    store.request_cancel(run_id)
    emit(store.get_run(run_id, include_report=False))


@app.command()
def resume(run_id: str, data_dir: Annotated[Path | None, typer.Option()] = None):
    from .jobs import reconcile_workers, spawn_worker
    store = Store(data_dir)
    reconcile_workers(store)
    store.prepare_resume(run_id)
    spawn_worker(store, run_id)
    emit(store.get_run(run_id, include_report=False))


@app.command()
def export(
    run_id: str, output: Annotated[Path, typer.Option()], format: str = "html",
    data_dir: Annotated[Path | None, typer.Option()] = None,
):
    """Export a completed report as JSON, CSV, HTML or Markdown."""
    from .exports import export_report
    run = Store(data_dir).get_run(run_id)
    if run["status"] != "completed":
        raise typer.BadParameter("The experiment has not completed")
    content, _, _ = export_report(run["report"], format)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")
    typer.echo(str(output.resolve()))


@app.command()
def research(
    study_id: str,
    request_file: Annotated[Path, typer.Option("--request", exists=True, dir_okay=False)],
    data_dir: Annotated[Path | None, typer.Option()] = None,
):
    """Run explicit research with the study's persistent provider-cost ledger."""
    from .services import research_study
    store = Store(data_dir)
    request = ResearchRequest.model_validate_json(request_file.read_text(encoding="utf-8-sig"))
    emit(asyncio.run(research_study(store, study_id, request)))


@app.command("import-mirofish")
def import_mirofish(
    study_id: str, source: Annotated[Path, typer.Argument(exists=True)],
    data_dir: Annotated[Path | None, typer.Option()] = None,
):
    """Import a read-only MiroFish export without loading or altering MiroFish."""
    from .memory import LocalMemory
    store = Store(data_dir)
    store.get_study(study_id)
    emit(LocalMemory(store.root / "memory.sqlite").import_mirofish(study_id, source))


@app.command("import-graphiti")
def import_graphiti(
    study_id: str, group_id: Annotated[str, typer.Option()], limit: int = 200,
    data_dir: Annotated[Path | None, typer.Option()] = None,
    env_file: Annotated[Path | None, typer.Option(exists=True, dir_okay=False)] = None,
):
    """Read a specific Graphiti namespace into local unverified beliefs; never write to Neo4j."""
    from .graphiti_bridge import GraphitiReadConnector
    from .memory import LocalMemory
    if env_file:
        from .settings import load_env_file
        load_env_file(env_file)
    store = Store(data_dir)
    store.get_study(study_id)
    with GraphitiReadConnector.from_env() as connector:
        result = connector.import_into(LocalMemory(store.root / "memory.sqlite"), study_id, group_id, limit)
    emit(result)


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    try:
        app()
    except (ValueError, KeyError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
