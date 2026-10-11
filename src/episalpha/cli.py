"""Command-line entry point for EpisAlpha (plan M4-T02).

A thin shell over :mod:`episalpha.research.services`: it parses arguments, calls a service and
prints the outcome. Exit codes: 0 completed · 2 invalid usage or request · 3 rejected · 4 failed
or timed out · 5 abstained or partial (incomplete) · 6 cancelled.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from episalpha import __version__
from episalpha.contracts.errors import EpisAlphaError, ErrorCode
from episalpha.contracts.research import (
    RETROSPECTIVE_NOTICE,
    ResearchMode,
    RunRecord,
    RuntimeMode,
)
from episalpha.knowledge.export_obsidian import export_run
from episalpha.observability import SpanKind, configure_tracing, shutdown_tracing, span, trace_url
from episalpha.research import services
from episalpha.research.artifacts import RunArtifacts
from episalpha.settings import load_settings

HELP = (
    "Evidence-grounded personal investment research workbench.\n\n"
    "Exit codes: 0 completed, 2 invalid usage or request, 3 rejected, 4 failed or timed out, "
    "5 abstained or partial, 6 cancelled."
)
DEFAULT_CONFIG = Path("config") / "demo.toml"

app = typer.Typer(
    add_completion=False, no_args_is_help=True, invoke_without_command=True, help=HELP
)
demo_app = typer.Typer(add_completion=False, no_args_is_help=True, help="Demo corpus.")
research_app = typer.Typer(add_completion=False, no_args_is_help=True, help="Research runs.")
app.add_typer(demo_app, name="demo")
export_app = typer.Typer(add_completion=False, no_args_is_help=True, help="Derived exports.")
app.add_typer(research_app, name="research")
app.add_typer(export_app, name="export")


def _now() -> datetime:
    return datetime.now(UTC)


@app.callback()
def main(
    context: typer.Context,
    version: Annotated[
        bool, typer.Option("--version", help="Print the installed EpisAlpha version.")
    ] = False,
    config: Annotated[
        Path | None,
        typer.Option(
            "--config", help="Settings file (default: $EPISALPHA_CONFIG or config/demo.toml)."
        ),
    ] = None,
) -> None:
    """Configure top-level CLI options."""
    if version:
        typer.echo(__version__)
        raise typer.Exit()
    context.obj = config or Path(os.environ.get("EPISALPHA_CONFIG") or DEFAULT_CONFIG)


def _workbench(context: typer.Context) -> services.Workbench:
    path = context.obj if isinstance(context.obj, Path) else DEFAULT_CONFIG
    if not path.is_file():
        _fail(f"settings file {path} not found")
    settings = load_settings(path)
    configure_tracing(settings)
    return services.open_workbench(settings)


def _fail(message: str, code: int = 2) -> None:
    typer.echo(f"error: {message}", err=True)
    shutdown_tracing()
    raise typer.Exit(code)


def _report(workbench: services.Workbench, record: RunRecord) -> None:
    request = record.request
    if request.runtime_mode is RuntimeMode.FAKE:
        typer.echo("[FIXTURE] fake runtime: scripted fixture output, not research")
    typer.echo(f"run_id: {request.run_id}")
    typer.echo(f"state: {record.state.value}")
    if record.reason:
        typer.echo(f"reason: {record.reason}")
    if record.error_code is not None:
        typer.echo(f"error_code: {record.error_code.value}")
    for warning in record.warnings:
        typer.echo(f"warning: {warning}")
    if request.research_mode is ResearchMode.HISTORICAL_RECONSTRUCTION:
        typer.echo(f"notice: {RETROSPECTIVE_NOTICE}")
    typer.echo(f"usage: {services.usage_line(record.usage)}")
    if record.thesis_id:
        typer.echo(f"thesis: {record.thesis_id}")
    artifacts = RunArtifacts(workbench.runs_dir, request.run_id)
    typer.echo(f"artifacts: {artifacts.directory}")
    try:
        trace_id = str(artifacts.index().get("trace_id") or "")
    except FileNotFoundError:
        trace_id = ""
    if trace_id:
        link = trace_url(trace_id)
        typer.echo(f"trace: {trace_id}" + (f" {link}" if link else ""))


def _finish(workbench: services.Workbench, record: RunRecord) -> None:
    _report(workbench, record)
    workbench.close()
    shutdown_tracing()
    raise typer.Exit(services.exit_code(record.state))


@demo_app.command("seed")
def demo_seed(context: typer.Context) -> None:
    """Load the synthetic demo corpus and the demo cases' instruments (idempotent)."""
    workbench = _workbench(context)
    with span("cli.demo.seed", SpanKind.CHAIN):
        counts = services.seed_demo(workbench)
    typer.echo("seeded: " + ", ".join(f"{name} {count}" for name, count in counts.items()))
    typer.echo(f"database: {workbench.data_root / 'app.sqlite3'}")
    workbench.close()
    shutdown_tracing()


@research_app.command("run")
def research_run(
    context: typer.Context,
    case: Annotated[
        str | None, typer.Option("--case", help="supported, conflicting or insufficient.")
    ] = None,
    snapshot: Annotated[
        str | None, typer.Option("--snapshot", help="Rerun on an existing snapshot.")
    ] = None,
    question: Annotated[
        str | None, typer.Option("--question", help="Required with --snapshot.")
    ] = None,
    runtime: Annotated[str, typer.Option("--runtime", help="fake or hermes.")] = "fake",
) -> None:
    """Admit a run, execute it here, and print the outcome."""
    if (case is None) == (snapshot is None):
        _fail("give exactly one of --case or --snapshot")
    if snapshot is not None and not question:
        _fail("--snapshot needs --question; the snapshot fixes cutoff and instrument only")
    if case is not None and question:
        _fail("--question applies to --snapshot; a case carries its own question")
    try:
        mode = RuntimeMode(runtime)
    except ValueError:
        _fail("--runtime must be fake or hermes")
        return
    workbench = _workbench(context)
    now = _now()
    try:
        with span("cli.research.run", SpanKind.CHAIN, **{"episalpha.runtime_mode": mode.value}):
            if case is not None:
                request, plan = services.plan_case(workbench, case, mode, now=now)
            else:
                assert snapshot is not None and question is not None
                request, plan = services.plan_snapshot(workbench, snapshot, question, mode, now=now)
            record = services.submit(workbench, request, plan)
        record = services.execute(
            workbench, record.request.run_id, worker_id=f"cli-{os.getpid()}", now=_now
        )
    except EpisAlphaError as error:
        workbench.close()
        _fail(str(error))
        return
    _finish(workbench, record)


@research_app.command("execute")
def research_execute(context: typer.Context, run_id: str) -> None:
    """Internal worker entry point: execute an already-admitted run. Never admits a job."""
    workbench = _workbench(context)
    try:
        with span("cli.research.execute", SpanKind.CHAIN):
            pass
        record = services.execute(workbench, run_id, worker_id=f"worker-{os.getpid()}", now=_now)
    except EpisAlphaError as error:
        workbench.close()
        _fail(str(error))
        return
    _finish(workbench, record)


@research_app.command("status")
def research_status(context: typer.Context, run_id: str) -> None:
    """Show a run's state, usage, artifacts and trace."""
    workbench = _workbench(context)
    with span("cli.research.status", SpanKind.CHAIN):
        record = workbench.repo.get_run(run_id)
    if record is None:
        workbench.close()
        _fail(f"run {run_id!r} does not exist")
        return
    _finish(workbench, record)


@research_app.command("cancel")
def research_cancel(context: typer.Context, run_id: str) -> None:
    """Request cancellation; the runner stops before its next stage."""
    workbench = _workbench(context)
    try:
        with span("cli.research.cancel", SpanKind.CHAIN):
            record = services.cancel(workbench, run_id, now=_now())
    except EpisAlphaError as error:
        workbench.close()
        _fail(str(error))
        return
    typer.echo(f"cancellation requested: {run_id} (state now {record.state.value})")
    workbench.close()
    shutdown_tracing()


@research_app.command("recover")
def research_recover(context: typer.Context, run_id: str) -> None:
    """Resume an interrupted run as a new attempt; completed stages are reused, not redone."""
    workbench = _workbench(context)
    try:
        with span("cli.research.recover", SpanKind.CHAIN):
            pass
        record = services.recover_run(
            workbench, run_id, worker_id=f"recover-{os.getpid()}", now=_now
        )
    except EpisAlphaError as error:
        workbench.close()
        _fail(str(error))
        return
    _finish(workbench, record)


@app.command("replay")
def replay(context: typer.Context, run_id: str) -> None:
    """Re-open a finished run from its saved artifacts, with zero model or network calls.

    Exit 0 when every artifact verifies; 4 on an integrity error; 2 for an unknown run.
    """
    workbench = _workbench(context)
    try:
        view = services.replay_run(workbench, run_id)
    except EpisAlphaError as error:
        workbench.close()
        code = 4 if error.code.value == "INTEGRITY_ERROR" else 2
        _fail(str(error), code)
        return
    record = view.record
    if record.request.runtime_mode is RuntimeMode.FAKE:
        typer.echo("[FIXTURE] fake runtime: scripted fixture output, not research")
    typer.echo(f"replay: {run_id} ({view.verified} artifacts verified, no model or network calls)")
    typer.echo(f"state: {record.state.value}")
    if record.reason:
        typer.echo(f"reason: {record.reason}")
    if view.index.get("prior_run_id"):
        typer.echo(f"prior run: {view.index['prior_run_id']}")
    if record.request.research_mode is ResearchMode.HISTORICAL_RECONSTRUCTION:
        typer.echo(f"notice: {RETROSPECTIVE_NOTICE}")
    if view.thesis is not None:
        typer.echo(f"stance: {view.thesis['stance']}")
        for assertion in view.thesis["assertions"]:
            refs = ", ".join([*assertion["claim_ids"], *assertion["hypothesis_ids"]])
            typer.echo(f"- [{assertion['section']}] {assertion['text']} ({refs})")
        for item in view.thesis["missing_information"]:
            typer.echo(f"missing: {item}")
    typer.echo(f"snapshot: {view.manifest['snapshot_id']} {view.manifest['snapshot_hash']}")
    typer.echo(f"trace: {view.index.get('trace_id', '')}")
    workbench.close()
    shutdown_tracing()


@export_app.command("obsidian")
def export_obsidian(
    context: typer.Context,
    run: Annotated[str, typer.Option("--run", help="The finished run to export.")],
    output: Annotated[
        Path | None,
        typer.Option("--output", help="Vault directory (default: <data_root>/exports/vault)."),
    ] = None,
) -> None:
    """Write a one-way, byte-stable Obsidian vault for one finished run.

    Notes go to generated/<run_id>/; annotations/ is never written. If the owner edited a
    generated note, the export moves to generated/<run_id>.<n>/ and leaves the edits untouched.
    Exit 0 on success; 2 for an unknown or unfinished run; 4 on an artifact integrity error.
    """
    workbench = _workbench(context)
    vault = output or workbench.data_root / "exports" / "vault"
    record = workbench.repo.get_run(run)
    try:
        result = export_run(workbench.repo, workbench.runs_dir, run, vault)
    except EpisAlphaError as error:
        workbench.close()
        _fail(str(error), 4 if error.code is ErrorCode.INTEGRITY_ERROR else 2)
        return
    except OSError as error:
        workbench.close()
        _fail(f"cannot write the vault at {vault}: {error.strerror or type(error).__name__}")
        return
    if record is not None and record.request.runtime_mode is RuntimeMode.FAKE:
        typer.echo("[FIXTURE] fake runtime: scripted fixture output, not research")
    relative = result.destination.relative_to(vault.resolve()).as_posix()
    typer.echo(f"exported: {run} -> {relative} ({result.files} files)")
    typer.echo(f"vault: {vault.resolve()}")
    typer.echo(f"manifest: {result.manifest_hash}")
    typer.echo(f"conflicts: {len(result.conflicts)}")
    for name in result.conflicts:
        typer.echo(f"edited, left untouched: generated/{name}")
    workbench.close()
    shutdown_tracing()


if __name__ == "__main__":  # the browser launches workers as ``python -m episalpha.cli``
    app()
