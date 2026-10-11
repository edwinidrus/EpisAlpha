"""Application services shared by the CLI and the browser (plan M4-T02, M5-T01).

The CLI and the UI stay thin: they call these functions and print or render the result. Nothing
here makes a model call by itself; :func:`execute` hands a claimed run to the runner with the
runtime the run was admitted for. The browser never executes a run on its render path: it
admits, then :func:`launch` starts one detached ``research execute`` worker.

Three evidence worlds, never mixed:

- **synthetic** (``eval_cases/demo/synthetic_corpus.json``): the fixture corpus that fake runs
  use. It belongs to "Synthetic Test Issuer NV" and is never attached to a real ticker;
- **case**: the real filings ingested for a demo case's CIK. With none ingested, a run abstains
  at freeze time, honestly, with no model call;
- **snapshot**: the documents of an existing frozen snapshot, for a fresh rerun.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from episalpha.contracts.errors import EpisAlphaError, ErrorCode
from episalpha.contracts.knowledge import (
    Entity,
    EvidenceDocument,
    EvidenceSpan,
    Instrument,
    TickerAlias,
)
from episalpha.contracts.research import (
    RETROSPECTIVE_NOTICE,
    TERMINAL_STATES,
    Budgets,
    ResearchMode,
    RunRecord,
    RunRequest,
    RunState,
    RuntimeMode,
    StageResult,
    Thesis,
    ThesisSection,
    Usage,
)
from episalpha.observability import trace_url
from episalpha.research.artifacts import ReplayView, RunArtifacts, replay
from episalpha.research.runner import (
    Evidence,
    EvidenceLoader,
    ResearchRunner,
    admit,
    claim,
    recover,
    request_cancel,
)
from episalpha.runtime.fake import FakeRuntime, Scenario
from episalpha.runtime.port import ResearchRuntimePort
from episalpha.settings import Settings
from episalpha.storage.db import open_database, transaction
from episalpha.storage.objects import ObjectStore
from episalpha.storage.repository import Repository

CASE_KINDS = {
    "supported": "supported thesis",
    "conflicting": "conflicting evidence",
    "insufficient": "insufficient evidence",
}
FAKE_SCENARIOS = {
    "supported": Scenario.COMPLETION,
    "conflicting": Scenario.COMPLETION,
    "insufficient": Scenario.ABSTENTION,
}
SYNTHETIC_CORPUS = Path("eval_cases") / "demo" / "synthetic_corpus.json"
SYNTHETIC_INSTRUMENT = "synthetic-issuer.eq"
HARNESS_ID = "harness.baseline"

EXIT_CODES: dict[RunState, int] = {
    RunState.RESEARCH_COMPLETED: 0,
    RunState.REJECTED: 3,
    RunState.FAILED: 4,
    RunState.TIMED_OUT: 4,
    RunState.ABSTAINED: 5,
    RunState.PARTIAL: 5,
    RunState.CANCELLED: 6,
}
"""0 completed · 2 invalid usage · 3 rejected · 4 failed/timed out · 5 abstained/partial
· 6 cancelled. A run that has not ended yet reports 0 from ``status``."""


def exit_code(state: RunState) -> int:
    return EXIT_CODES.get(state, 0)


def _refuse(message: str) -> EpisAlphaError:
    return EpisAlphaError(ErrorCode.INVALID_REQUEST, message)


# --- the workbench --------------------------------------------------------------------------


@dataclass
class Workbench:
    settings: Settings
    repo: Repository
    objects: ObjectStore

    @property
    def project_root(self) -> Path:
        return self.settings.paths.project_root

    @property
    def data_root(self) -> Path:
        return self.settings.paths.data_root

    @property
    def runs_dir(self) -> Path:
        return self.data_root / "runs"

    def close(self) -> None:
        self.repo.connection.close()


def open_workbench(settings: Settings) -> Workbench:
    settings.paths.data_root.mkdir(parents=True, exist_ok=True)
    connection = open_database(settings.paths.data_root / "app.sqlite3")
    return Workbench(
        settings, Repository(connection), ObjectStore(settings.paths.data_root / "objects")
    )


# --- cases ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class Case:
    name: str
    case_id: str
    ticker: str
    cik: str
    instrument_id: str
    question: str
    research_cutoff: datetime
    research_mode: ResearchMode
    status: str


def load_cases(project_root: Path) -> dict[str, Case]:
    """The three demo cases, by short name, from ``eval_cases/manifests``."""
    by_kind = {kind: name for name, kind in CASE_KINDS.items()}
    cases: dict[str, Case] = {}
    for path in sorted((project_root / "eval_cases" / "manifests").glob("*.json")):
        raw = json.loads(path.read_text())
        name = by_kind.get(raw.get("intended_case", ""))
        if name is None:
            continue
        cases[name] = Case(
            name=name,
            case_id=raw["case_id"],
            ticker=raw["ticker"],
            cik=raw["cik"],
            instrument_id=raw["instrument_id"],
            question=raw["question"],
            research_cutoff=datetime.fromisoformat(raw["research_cutoff"]),
            research_mode=ResearchMode(raw["research_mode"]),
            status=raw.get("status", ""),
        )
    return cases


def _synthetic_corpus(project_root: Path) -> dict[str, Any]:
    return json.loads((project_root / SYNTHETIC_CORPUS).read_text())  # type: ignore[no-any-return]


def seed_demo(workbench: Workbench) -> dict[str, int]:
    """Load the synthetic corpus and the real cases' instruments. Idempotent."""
    corpus = _synthetic_corpus(workbench.project_root)
    records: list[Any] = [
        *(Entity.model_validate(item) for item in corpus["entities"]),
        *(Instrument.model_validate(item) for item in corpus["instruments"]),
        *(EvidenceDocument.model_validate(item) for item in corpus["documents"]),
        *(EvidenceSpan.model_validate(item) for item in corpus["spans"]),
    ]
    for case in load_cases(workbench.project_root).values():
        entity_id = case.instrument_id.removesuffix(".eq")
        records.append(
            Entity(
                entity_id=entity_id,
                kind="corporation",
                canonical_name=case.ticker,
                external_identifiers={"sec_cik": case.cik},
            )
        )
        records.append(
            Instrument(
                instrument_id=case.instrument_id,
                issuer_entity_id=entity_id,
                exchange="US",
                currency="USD",
                ticker_aliases=(
                    TickerAlias(ticker=case.ticker, valid_from=datetime(2000, 1, 1, tzinfo=UTC)),
                ),
            )
        )
    with transaction(workbench.repo.connection):
        workbench.repo.save_all(records)
    for text in corpus["document_texts"].values():
        workbench.objects.put(text.encode("utf-8"))
    return {
        "entities": sum(isinstance(r, Entity) for r in records),
        "instruments": sum(isinstance(r, Instrument) for r in records),
        "documents": len(corpus["documents"]),
        "spans": len(corpus["spans"]),
    }


# --- evidence loaders -----------------------------------------------------------------------


def synthetic_loader(workbench: Workbench) -> EvidenceLoader:
    corpus = _synthetic_corpus(workbench.project_root)

    def load(request: RunRequest) -> Evidence:
        return Evidence(
            documents=tuple(EvidenceDocument.model_validate(d) for d in corpus["documents"]),
            spans=tuple(EvidenceSpan.model_validate(s) for s in corpus["spans"]),
            document_texts=dict(corpus["document_texts"]),
            entities=tuple(Entity.model_validate(e) for e in corpus["entities"]),
            instruments=tuple(Instrument.model_validate(i) for i in corpus["instruments"]),
            source_version="synthetic-demo-1",
        )

    return load


def _documents_with_texts(
    workbench: Workbench, documents: list[EvidenceDocument]
) -> tuple[list[EvidenceDocument], list[EvidenceSpan], dict[str, str]]:
    spans: list[EvidenceSpan] = []
    texts: dict[str, str] = {}
    kept: list[EvidenceDocument] = []
    for document in documents:
        if not workbench.objects.exists(document.parsed_text_hash):
            continue
        texts[document.document_id] = workbench.objects.get(document.parsed_text_hash).decode()
        kept.append(document)
        spans.extend(workbench.repo.spans_for_document(document.document_id))
    return kept, spans, texts


def case_loader(workbench: Workbench, case: Case) -> EvidenceLoader:
    """The real filings ingested for the case's CIK (EDGAR and XBRL lineages)."""

    def load(request: RunRequest) -> Evidence:
        rows = workbench.repo.connection.execute(
            "SELECT payload FROM evidence_document WHERE source_family_id LIKE ? "
            "OR source_family_id LIKE ? ORDER BY document_id",
            (f"sec-{case.cik}-%", f"xbrl-{case.cik}-%"),
        ).fetchall()
        documents = [EvidenceDocument.model_validate_json(row["payload"]) for row in rows]
        kept, spans, texts = _documents_with_texts(workbench, documents)
        instrument = workbench.repo.get_instrument(case.instrument_id)
        entity = workbench.repo.get_entity(case.instrument_id.removesuffix(".eq"))
        return Evidence(
            documents=tuple(kept),
            spans=tuple(spans),
            document_texts=texts,
            entities=(entity,) if entity else (),
            instruments=(instrument,) if instrument else (),
            source_version=f"case-{case.case_id}",
            price_source_id=workbench.settings.sources.price_source_id,
        )

    return load


def snapshot_loader(workbench: Workbench, snapshot_id: str) -> tuple[EvidenceLoader, str, datetime]:
    """Rebuild the evidence of an existing snapshot. Returns the loader, instrument, cutoff."""
    manifest = workbench.repo.get_snapshot(snapshot_id)
    if manifest is None:
        raise _refuse(f"snapshot {snapshot_id!r} does not exist")
    if len(manifest.instrument_ids) != 1:
        raise _refuse(
            f"snapshot {snapshot_id!r} covers {len(manifest.instrument_ids)} instruments; v0.1 "
            "writes one thesis about one instrument"
        )
    documents = [
        document
        for document_id in manifest.document_ids
        if (document := workbench.repo.get_document(document_id)) is not None
    ]
    kept, spans, texts = _documents_with_texts(workbench, documents)
    instrument_id = manifest.instrument_ids[0]
    instrument = workbench.repo.get_instrument(instrument_id)
    entity = workbench.repo.get_entity(instrument.issuer_entity_id) if instrument else None
    claims = tuple(
        claim_
        for claim_id in manifest.permitted_claim_ids
        if (claim_ := workbench.repo.get_claim(claim_id)) is not None
    )

    def load(request: RunRequest) -> Evidence:
        return Evidence(
            documents=tuple(kept),
            spans=tuple(s for s in spans if s.span_id in manifest.permitted_span_ids),
            document_texts=texts,
            claims=claims,
            entities=(entity,) if entity else (),
            instruments=(instrument,) if instrument else (),
            source_version=manifest.source_version,
        )

    return load, instrument_id, manifest.research_cutoff


# --- submission and execution ----------------------------------------------------------------


def new_request(
    workbench: Workbench,
    *,
    source: str,
    instrument_id: str,
    question: str,
    research_cutoff: datetime,
    research_mode: ResearchMode,
    runtime_mode: RuntimeMode,
    now: datetime,
) -> RunRequest:
    """A request whose idempotency key covers what it asks, so a resubmission finds its run."""
    limits = workbench.settings.limits
    material = json.dumps(
        [
            source,
            instrument_id,
            question,
            research_cutoff.isoformat(),
            runtime_mode.value,
            HARNESS_ID,
        ]
    )
    return RunRequest(
        run_id=f"run-{uuid.uuid4().hex[:12]}",
        idempotency_key=f"key-{hashlib.sha256(material.encode()).hexdigest()[:24]}",
        instrument_id=instrument_id,
        question=question,
        research_cutoff=research_cutoff,
        research_mode=research_mode,
        runtime_mode=runtime_mode,
        harness_id=HARNESS_ID,
        budgets=Budgets(
            run_wall_time_seconds=limits.run_wall_time_seconds,
            max_model_requests=limits.max_model_requests,
            max_tool_calls=limits.max_tool_calls,
            max_output_tokens_per_call=limits.max_output_tokens_per_call,
        ),
        requested_at=now,
    )


def _source(base: str, nonce: str) -> str:
    # A browser form adds its nonce, so a new form is a new request; the CLI adds none.
    return f"{base}#{nonce}" if nonce else base


def plan_case(
    workbench: Workbench, case: str, mode: RuntimeMode, *, now: datetime, nonce: str = ""
) -> tuple[RunRequest, dict[str, Any]]:
    """The request and execution plan for a demo case.

    A fake run reads the synthetic corpus and is attached to the synthetic issuer, never to the
    case's real ticker; a Hermes run reads the filings ingested for the case's CIK.
    """
    cases = load_cases(workbench.project_root)
    if case not in cases:
        raise _refuse(f"unknown case {case!r}; choose {sorted(cases)}")
    chosen = cases[case]
    fake = mode is RuntimeMode.FAKE
    plan = {
        "evidence": "synthetic" if fake else "case",
        "case": case,
        "fake_scenario": FAKE_SCENARIOS[case].value,
    }
    request = new_request(
        workbench,
        source=_source(f"case:{case}:{'synthetic' if fake else 'filings'}", nonce),
        instrument_id=SYNTHETIC_INSTRUMENT if fake else chosen.instrument_id,
        question=chosen.question,
        research_cutoff=chosen.research_cutoff,
        research_mode=chosen.research_mode,
        runtime_mode=mode,
        now=now,
    )
    return request, plan


def plan_snapshot(
    workbench: Workbench,
    snapshot_id: str,
    question: str,
    mode: RuntimeMode,
    *,
    now: datetime,
    nonce: str = "",
) -> tuple[RunRequest, dict[str, Any]]:
    """A fresh run on an existing snapshot, linked to the first run that used it."""
    if not question.strip():
        raise _refuse("a snapshot rerun needs a question; the snapshot fixes cutoff and instrument")
    _, instrument, cutoff = snapshot_loader(workbench, snapshot_id)
    plan = {
        "evidence": "snapshot",
        "snapshot_id": snapshot_id,
        "prior_run_id": prior_run_for_snapshot(workbench, snapshot_id),
        "fake_scenario": FAKE_SCENARIOS["supported"].value,
    }
    request = new_request(
        workbench,
        source=_source(f"snapshot:{snapshot_id}", nonce),
        instrument_id=instrument,
        question=question,
        research_cutoff=cutoff,
        research_mode=ResearchMode.HISTORICAL_RECONSTRUCTION,
        runtime_mode=mode,
        now=now,
    )
    return request, plan


def submit(workbench: Workbench, request: RunRequest, plan: dict[str, Any]) -> RunRecord:
    """Admit a run and record how to execute it (``submission.json``). Idempotent.

    A new Hermes run is refused *before* admission when its runtime could not start, so a run
    that can never execute does not occupy v0.1's single job slot.
    """
    is_new = workbench.repo.run_by_idempotency_key(request.idempotency_key) is None
    if is_new and request.runtime_mode is RuntimeMode.HERMES:
        _hermes_readiness(workbench)
    record = admit(workbench.repo, request, now=request.requested_at)
    sidecar = workbench.runs_dir / record.request.run_id / "submission.json"
    if not sidecar.exists():
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        sidecar.write_text(json.dumps(plan, sort_keys=True))
    return record


def submission_plan(workbench: Workbench, run_id: str) -> dict[str, Any]:
    path = workbench.runs_dir / run_id / "submission.json"
    if not path.is_file():
        raise _refuse(f"run {run_id!r} has no submission record")
    return json.loads(path.read_text())  # type: ignore[no-any-return]


def launch(workbench: Workbench, run_id: str, config: Path, *, now: datetime) -> bool:
    """Start the detached ``research execute`` worker for a queued run, at most once.

    The guard is the exclusively created ``launch.json``, in persistence rather than in a
    browser session: a rerun, a second click or a page refresh finds it and launches nothing.
    Returns whether this call launched the worker.
    """
    record = workbench.repo.get_run(run_id)
    if record is None:
        raise _refuse(f"run {run_id!r} has not been admitted")
    if record.state is not RunState.QUEUED:
        return False
    directory = workbench.runs_dir / run_id
    directory.mkdir(parents=True, exist_ok=True)
    try:
        with (directory / "launch.json").open("x") as marker:
            marker.write(json.dumps({"launched_at": now.isoformat()}))
    except FileExistsError:
        return False
    command = [
        *(sys.executable, "-m", "episalpha.cli", "--config", str(config.resolve())),
        *("research", "execute", run_id),
    ]
    _spawn(command, workbench.project_root, directory / "worker.log")
    return True


def _spawn(command: list[str], cwd: Path, log: Path) -> None:
    # ponytail: the browser process never waits; Python reaps the exited child on a later
    # Popen. A supervisor would replace this if v0.1 ever ran more than one job.
    with log.open("ab") as output:
        subprocess.Popen(
            command,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )


def _loader_for(workbench: Workbench, plan: dict[str, Any]) -> EvidenceLoader:
    kind = plan.get("evidence")
    if kind == "synthetic":
        return synthetic_loader(workbench)
    if kind == "case":
        return case_loader(workbench, load_cases(workbench.project_root)[plan["case"]])
    if kind == "snapshot":
        return snapshot_loader(workbench, plan["snapshot_id"])[0]
    raise _refuse(f"unknown evidence kind {kind!r}")


def execute(
    workbench: Workbench, run_id: str, *, worker_id: str, now: Callable[[], datetime]
) -> RunRecord:
    """Claim an admitted run and drive it to a terminal state. Never admits a job."""
    record = workbench.repo.get_run(run_id)
    if record is None:
        raise _refuse(f"run {run_id!r} has not been admitted")
    if record.state is not RunState.QUEUED:
        return record
    plan = submission_plan(workbench, run_id)
    claim(workbench.repo, run_id, worker_id, now=now())
    runner = _runner(workbench, plan, now)
    runtime, cleanup = _runtime_for(workbench, record, runner, plan)
    try:
        return runner.execute(run_id, runtime)
    finally:
        cleanup()


def _runner(
    workbench: Workbench, plan: dict[str, Any], now: Callable[[], datetime]
) -> ResearchRunner:
    lineage = {"prior_run_id": plan["prior_run_id"]} if plan.get("prior_run_id") else None
    return ResearchRunner(
        workbench.repo,
        workbench.objects,
        workbench.settings,
        _loader_for(workbench, plan),
        artifacts_root=workbench.runs_dir,
        now=now,
        lineage=lineage,
    )


def recover_run(
    workbench: Workbench, run_id: str, *, worker_id: str, now: Callable[[], datetime]
) -> RunRecord:
    """Resume an interrupted run as a new attempt (``research recover``)."""
    record = workbench.repo.get_run(run_id)
    if record is None:
        raise _refuse(f"run {run_id!r} does not exist")
    plan = submission_plan(workbench, run_id)
    runner = _runner(workbench, plan, now)
    runtime, cleanup = _runtime_for(workbench, record, runner, plan)
    try:
        return recover(workbench.repo, runner, run_id, runtime, worker_id=worker_id, now=now())
    finally:
        cleanup()


def replay_run(workbench: Workbench, run_id: str) -> ReplayView:
    """Re-open a finished run from its artifacts: zero model or network calls."""
    return replay(workbench.repo, workbench.runs_dir, run_id)


def prior_run_for_snapshot(workbench: Workbench, snapshot_id: str) -> str | None:
    row = workbench.repo.connection.execute(
        "SELECT run_id FROM run WHERE snapshot_id = ? ORDER BY started_at LIMIT 1",
        (snapshot_id,),
    ).fetchone()
    return str(row["run_id"]) if row else None


def _runtime_for(
    workbench: Workbench, record: RunRecord, runner: ResearchRunner, plan: dict[str, Any]
) -> tuple[ResearchRuntimePort, Callable[[], None]]:
    if record.request.runtime_mode is RuntimeMode.FAKE:
        scenario = Scenario(os.environ.get("EPISALPHA_FAKE_SCENARIO") or plan["fake_scenario"])
        return FakeRuntime(workbench.objects, scenario), lambda: None
    return _hermes_runtime(workbench, runner)


def _hermes_readiness(workbench: Workbench) -> tuple[dict[str, Any], str | None]:
    """Refuse unless a Hermes run could start: route credential exported, a worker available.

    Returns the runtime lock and the worker image ID (``None`` for the local worker).
    """
    route = workbench.settings.provider
    if route.credential() is None or route.model_id is None:
        raise _refuse(f"the model route credential {route.api_key_env!r} is not exported")
    lock = json.loads((workbench.project_root / "config" / "runtime.lock.json").read_text())
    if os.environ.get("EPISALPHA_WORKER") == "local":
        return lock, None
    image = lock.get("hermes", {}).get("worker_image", {}).get("id")
    if not image or not shutil.which("docker"):
        raise _refuse("no isolated worker available: build the worker image (M3-T04) first")
    from episalpha.runtime import sandbox

    try:
        config = sandbox.sandbox_config(str(image), os.environ)
    except ValueError as error:
        raise _refuse(f"no isolated worker available: {error}") from None
    problem = sandbox.preflight(config, sandbox._docker)
    if problem is not None:
        raise _refuse(f"no isolated worker available: {problem}")
    return lock, str(image)


def _hermes_runtime(
    workbench: Workbench, runner: ResearchRunner
) -> tuple[ResearchRuntimePort, Callable[[], None]]:
    # Imported here: the fake path needs none of the Hermes machinery.
    from episalpha.runtime.hermes import HermesRuntime, LocalLauncher, WorkerLauncher, load_harness
    from episalpha.runtime.model_relay import ModelRelay, RelayServer
    from episalpha.runtime.sandbox import SandboxLauncher, sandbox_config

    settings = workbench.settings
    route = settings.provider
    lock, image = _hermes_readiness(workbench)
    assert route.model_id is not None
    launcher: WorkerLauncher
    stage_root: Path | None = None
    if os.environ.get("EPISALPHA_WORKER") == "local":
        vendor = workbench.project_root / ".episalpha" / "vendor"
        launcher = LocalLauncher(
            [
                str(vendor / "hermes-venv" / "bin" / "python"),
                str(workbench.project_root / "worker" / "hermes_stage.py"),
            ],
            cwd=vendor / "hermes-agent",
        )
    else:
        assert image is not None
        sandbox_settings = sandbox_config(image, os.environ)
        launcher = SandboxLauncher(sandbox_settings)
        stage_root = sandbox_settings.stage_root
    token = secrets.token_hex(16)
    relay = ModelRelay(
        route,
        settings.limits,
        token,
        no_fallbacks=bool(
            lock.get("model_route", {})
            .get("observed_capabilities", {})
            .get("no_fallbacks_accepted")
        ),
        deadline=time.monotonic() + settings.limits.run_wall_time_seconds,
    )
    server = RelayServer(relay, host=launcher.bind_host, port=0)
    server.start()
    runtime = HermesRuntime(
        harness=load_harness(workbench.project_root / "harnesses" / "baseline"),
        relay=relay,
        relay_port=server.port,
        relay_token=token,
        model_id=route.model_id,
        limits=settings.limits,
        object_store=workbench.objects,
        tools_for=runner.tools_for,
        brief_for=runner.brief_for,
        launcher=launcher,
        work_dir=stage_root or workbench.data_root / "work",
    )
    return runtime, server.stop


def cancel(workbench: Workbench, run_id: str, *, now: datetime) -> RunRecord:
    record = workbench.repo.get_run(run_id)
    if record is None:
        raise _refuse(f"run {run_id!r} does not exist")
    request_cancel(workbench.repo, run_id, now=now)
    return record


# --- reading runs back (CLI status, browser) ------------------------------------------------


def usage_line(usage: Usage) -> str:
    """Reported usage; a count the provider did not report is "unknown", never 0."""
    tokens = (
        f"{usage.prompt_tokens}/{usage.completion_tokens}"
        if usage.prompt_tokens is not None and usage.completion_tokens is not None
        else "unknown"
    )
    return (
        f"model requests {usage.model_requests}, tool calls {usage.tool_calls}, "
        f"tokens (prompt/completion) {tokens}, cost unknown"
    )


def recent_runs(workbench: Workbench, *, limit: int = 20) -> list[RunRecord]:
    rows = workbench.repo.connection.execute(
        "SELECT run_id FROM run ORDER BY started_at DESC, rowid DESC LIMIT ?", (limit,)
    ).fetchall()
    return [run for row in rows if (run := workbench.repo.get_run(row["run_id"])) is not None]


@dataclass(frozen=True)
class Reference:
    """One record an assertion cites, with the status chips the reader must see."""

    record_id: str
    epistemic_status: str
    review_status: str


@dataclass(frozen=True)
class AssertionView:
    section: ThesisSection
    text: str
    references: tuple[Reference, ...]


@dataclass(frozen=True)
class RunView:
    """Everything the browser shows about one run, read from persistence and artifacts."""

    record: RunRecord
    stages: tuple[StageResult, ...]
    provenance: dict[str, Any]
    trace_link: str | None
    elapsed_seconds: int
    thesis: Thesis | None = None
    assertions: tuple[AssertionView, ...] = ()
    verified_artifacts: int = 0
    integrity_error: str | None = None

    @property
    def fixture(self) -> bool:
        return self.record.request.runtime_mode is RuntimeMode.FAKE

    @property
    def finished(self) -> bool:
        return self.record.state in TERMINAL_STATES

    @property
    def notice(self) -> str | None:
        mode = self.record.request.research_mode
        return RETROSPECTIVE_NOTICE if mode is ResearchMode.HISTORICAL_RECONSTRUCTION else None


def run_view(workbench: Workbench, run_id: str, *, now: datetime) -> RunView:
    """One run as stored. A finished run's thesis comes from its verified saved artifacts."""
    record = workbench.repo.get_run(run_id)
    if record is None:
        raise _refuse(f"run {run_id!r} does not exist")
    provenance = RunArtifacts(workbench.runs_dir, run_id).provenance
    trace_id = provenance.get("trace_id")
    view = RunView(
        record=record,
        stages=workbench.repo.stage_results(run_id),
        provenance=provenance,
        trace_link=trace_url(trace_id) if trace_id else None,
        elapsed_seconds=max(0, int(((record.ended_at or now) - record.started_at).total_seconds())),
    )
    if record.state not in TERMINAL_STATES or record.snapshot_id is None:
        return view
    try:
        saved = replay_run(workbench, run_id)
    except EpisAlphaError as error:
        return replace(view, integrity_error=str(error))
    if saved.thesis is None:
        return replace(view, verified_artifacts=saved.verified)
    thesis = Thesis.model_validate(saved.thesis)
    statuses = {item["claim_id"]: item["epistemic_status"] for item in saved.records["claims"]}
    # A hypothesis is hypothesized by definition; the contract has no status field for it.
    statuses |= {item["hypothesis_id"]: "hypothesized" for item in saved.records["hypotheses"]}
    assertions = tuple(
        AssertionView(
            section=assertion.section,
            text=assertion.text,
            references=tuple(
                _reference(workbench, record_id, statuses)
                for record_id in (*assertion.claim_ids, *assertion.hypothesis_ids)
            ),
        )
        for assertion in thesis.assertions
    )
    return replace(view, thesis=thesis, assertions=assertions, verified_artifacts=saved.verified)


def _reference(workbench: Workbench, record_id: str, statuses: dict[str, str]) -> Reference:
    epistemic = statuses.get(record_id)
    if epistemic is None:  # a snapshot claim, not one this run created
        claim_ = workbench.repo.get_claim(record_id)
        epistemic = claim_.epistemic_status.value if claim_ is not None else "unknown"
    assessment = workbench.repo.current_assessment(record_id)
    review = assessment.judgment.value if assessment is not None else "unreviewed"
    return Reference(record_id=record_id, epistemic_status=epistemic, review_status=review)
