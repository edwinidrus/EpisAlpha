"""M4-T01 — the research runner drives a run to an honest terminal state.

Every run here uses ``FakeRuntime`` on the SYNTHETIC snapshot: fixture output, never evidence
that a live integration works.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fixtures.synthetic_knowledge import (
    DEMAND_SPAN,
    DOCUMENT_TEXT,
    REVENUE_SPAN,
    SYNTHETIC_DOCUMENT,
    SYNTHETIC_ENTITY,
    SYNTHETIC_INSTRUMENT,
)
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from episalpha.contracts.errors import EpisAlphaError, ErrorCode
from episalpha.contracts.knowledge import Claim, EpistemicStatus
from episalpha.contracts.research import (
    Budgets,
    ResearchMode,
    RunRequest,
    RunState,
    RuntimeMode,
)
from episalpha.observability import configure_tracing, shutdown_tracing
from episalpha.research.artifacts import RunArtifacts
from episalpha.research.runner import Evidence, ResearchRunner, admit, claim, request_cancel
from episalpha.runtime.fake import FakeRuntime, Scenario
from episalpha.settings import Settings
from episalpha.storage.db import open_database
from episalpha.storage.objects import ObjectStore
from episalpha.storage.repository import Repository

NOW = datetime(2026, 10, 11, 7, 0, tzinfo=UTC)
CUTOFF = datetime(2026, 9, 21, tzinfo=UTC)


def evidence(request: RunRequest) -> Evidence:
    return Evidence(
        documents=(SYNTHETIC_DOCUMENT,),
        spans=(REVENUE_SPAN, DEMAND_SPAN),
        document_texts={"synthetic-doc.v1": DOCUMENT_TEXT},
        entities=(SYNTHETIC_ENTITY,),
        instruments=(SYNTHETIC_INSTRUMENT,),
    )


def no_evidence(request: RunRequest) -> Evidence:
    return Evidence(entities=(SYNTHETIC_ENTITY,), instruments=(SYNTHETIC_INSTRUMENT,))


def make_request(run_id: str = "run-0001", key: str = "key-0001") -> RunRequest:
    return RunRequest(
        run_id=run_id,
        idempotency_key=key,
        instrument_id="synthetic-issuer.eq",
        question="Did the issuer signal weaker demand, and what revenue did it report?",
        research_cutoff=CUTOFF,
        research_mode=ResearchMode.HISTORICAL_RECONSTRUCTION,
        runtime_mode=RuntimeMode.FAKE,
        harness_id="harness.baseline",
        budgets=Budgets(
            run_wall_time_seconds=300,
            max_model_requests=8,
            max_tool_calls=12,
            max_output_tokens_per_call=4000,
        ),
        requested_at=NOW,
    )


@pytest.fixture
def world(tmp_path: Path) -> Iterator[dict[str, Any]]:
    connection = open_database(tmp_path / "app.sqlite3")
    settings = Settings.model_validate(
        {"paths": {"project_root": tmp_path, "data_root": tmp_path / "data"}}
    )
    yield {
        "repo": Repository(connection),
        "objects": ObjectStore(tmp_path / "objects"),
        "settings": settings,
        "tmp": tmp_path,
    }
    connection.close()


def runner(world: dict[str, Any], loader: Any = evidence) -> ResearchRunner:
    return ResearchRunner(
        world["repo"],
        world["objects"],
        world["settings"],
        loader,
        artifacts_root=world["tmp"] / "runs",
        now=lambda: NOW,
    )


def run(world: dict[str, Any], scenario: Scenario, loader: Any = evidence) -> Any:
    repo = world["repo"]
    request = make_request()
    admit(repo, request, now=NOW)
    claim(repo, request.run_id, "worker-1", now=NOW)
    return runner(world, loader).execute(
        request.run_id, FakeRuntime(world["objects"], scenario, now=lambda: NOW)
    )


# --- terminal states -------------------------------------------------------------------------


def test_completion(world: dict[str, Any]) -> None:
    record = run(world, Scenario.COMPLETION)
    repo: Repository = world["repo"]

    assert record.state is RunState.RESEARCH_COMPLETED, record.reason
    assert record.thesis_id == "run-0001.thesis"
    thesis = repo.get_thesis("run-0001.thesis")
    assert thesis is not None
    assert thesis.model_identifier == "fixture"
    assert [a.assertion_id for a in thesis.assertions][:2] == ["run-0001.a1", "run-0001.a2"]
    claim_c1 = repo.get_claim("run-0001.c1")
    assert claim_c1 is not None and claim_c1.run_id == "run-0001"
    assert repo.get_hypothesis("run-0001.h1") is not None
    assert record.validation_report is not None and record.validation_report.structurally_valid
    stages = repo.stage_results("run-0001")
    assert [(s.stage, s.completed) for s in stages] == [
        (RunState.RESEARCHING, True),
        (RunState.CRITIQUING, True),
        (RunState.SYNTHESIZING, True),
    ]
    assert record.usage.model_requests == 6
    index = RunArtifacts(world["tmp"] / "runs", "run-0001").index()
    assert index["runtime"] == "fake"
    assert len(index["trace_id"]) == 32
    assert index["snapshot_hash"] == repo.get_snapshot(record.snapshot_id).snapshot_hash
    assert {"manifest", "records", "thesis", "validation", "stages/researching-1"} <= set(
        index["artifacts"]
    )


def test_missing_essential_evidence_abstains_before_any_stage(world: dict[str, Any]) -> None:
    record = run(world, Scenario.COMPLETION, loader=no_evidence)
    assert record.state is RunState.ABSTAINED
    assert "essential evidence" in record.reason
    assert record.error_code is None
    assert world["repo"].stage_results("run-0001") == ()


def test_a_synthesized_abstain_stance_is_an_abstention(world: dict[str, Any]) -> None:
    record = run(world, Scenario.ABSTENTION)
    assert record.state is RunState.ABSTAINED
    assert record.thesis_id == "run-0001.thesis"


def test_invalid_references_are_repaired_once(world: dict[str, Any]) -> None:
    record = run(world, Scenario.REPAIRED)
    assert record.state is RunState.RESEARCH_COMPLETED, record.reason
    stages = [s.stage for s in world["repo"].stage_results("run-0001")]
    assert stages.count(RunState.RESEARCHING) == 2
    assert any("repair" in warning for warning in record.warnings)
    artifacts = RunArtifacts(world["tmp"] / "runs", "run-0001")
    first = artifacts.read("stages/researching-1")
    assert first["payload"]["claims"][0]["span_ids"] == ["synthetic-span.fabricated"]


def test_unrepairable_references_are_rejected(world: dict[str, Any]) -> None:
    record = run(world, Scenario.INVALID_REFERENCES)
    assert record.state is RunState.REJECTED
    assert record.error_code is ErrorCode.INVALID_OUTPUT
    assert "synthetic-span.fabricated" in record.reason
    assert world["repo"].get_claim("run-0001.c1") is None


def test_provider_failure_is_failed_never_abstained(world: dict[str, Any]) -> None:
    record = run(world, Scenario.PROVIDER_FAILURE)
    assert record.state is RunState.FAILED
    assert record.error_code is ErrorCode.SOURCE_FAILED
    (stage,) = world["repo"].stage_results("run-0001")
    assert stage.completed is False  # an interrupted stage never shows as completed
    assert "stages/researching-1" in RunArtifacts(world["tmp"] / "runs", "run-0001").hashes


def test_timeout(world: dict[str, Any]) -> None:
    record = run(world, Scenario.TIMEOUT)
    assert record.state is RunState.TIMED_OUT
    assert record.error_code is ErrorCode.BUDGET_EXCEEDED


def test_cancellation_scripted(world: dict[str, Any]) -> None:
    assert run(world, Scenario.CANCELLATION).state is RunState.CANCELLED


def test_cancellation_requested_before_a_stage(world: dict[str, Any]) -> None:
    repo = world["repo"]
    request = make_request()
    admit(repo, request, now=NOW)
    claim(repo, request.run_id, "worker-1", now=NOW)
    request_cancel(repo, request.run_id, now=NOW)
    record = runner(world).execute(
        request.run_id, FakeRuntime(world["objects"], Scenario.COMPLETION, now=lambda: NOW)
    )
    assert record.state is RunState.CANCELLED
    assert repo.stage_results(request.run_id) == ()


def test_partial_result_keeps_the_work(world: dict[str, Any]) -> None:
    record = run(world, Scenario.PARTIAL)
    assert record.state is RunState.PARTIAL
    assert world["repo"].get_claim("run-0001.c1") is not None
    assert record.thesis_id is None


# --- admission and claims --------------------------------------------------------------------


def test_same_idempotency_key_returns_the_same_run(world: dict[str, Any]) -> None:
    repo = world["repo"]
    first = admit(repo, make_request(), now=NOW)
    again = admit(repo, make_request(run_id="run-0002"), now=NOW)
    assert again.request.run_id == first.request.run_id == "run-0001"


def test_a_second_active_job_is_refused(world: dict[str, Any]) -> None:
    repo = world["repo"]
    admit(repo, make_request(), now=NOW)
    with pytest.raises(EpisAlphaError) as raised:
        admit(repo, make_request(run_id="run-0002", key="key-0002"), now=NOW)
    assert raised.value.code is ErrorCode.INVALID_REQUEST


def test_a_double_claim_is_refused(world: dict[str, Any]) -> None:
    repo = world["repo"]
    admit(repo, make_request(), now=NOW)
    claim(repo, "run-0001", "worker-1", now=NOW)
    with pytest.raises(EpisAlphaError) as raised:
        claim(repo, "run-0001", "worker-2", now=NOW)
    assert raised.value.code is ErrorCode.INVALID_REQUEST


def test_an_unclaimed_run_is_not_executed(world: dict[str, Any]) -> None:
    repo = world["repo"]
    admit(repo, make_request(), now=NOW)
    with pytest.raises(EpisAlphaError):
        runner(world).execute(
            "run-0001", FakeRuntime(world["objects"], Scenario.COMPLETION, now=lambda: NOW)
        )


def test_a_canonical_id_cannot_be_overwritten(world: dict[str, Any]) -> None:
    repo: Repository = world["repo"]
    existing = Claim(
        claim_id="run-0001.c1",
        statement="An earlier canonical claim that must survive.",
        subject_ids=("synthetic-issuer.eq",),
        attribution="earlier run",
        epistemic_status=EpistemicStatus.REPORTED,
        span_ids=("synthetic-span.revenue",),
        created_at=NOW,
    )
    repo.save_all([SYNTHETIC_ENTITY, SYNTHETIC_INSTRUMENT, SYNTHETIC_DOCUMENT, REVENUE_SPAN])
    repo.save_claim(existing)
    record = run(world, Scenario.COMPLETION)
    assert record.state is RunState.REJECTED
    assert "already exists" in record.reason
    assert repo.get_claim("run-0001.c1") == existing


# --- the story of a run ----------------------------------------------------------------------


def test_one_trace_tells_the_whole_run(world: dict[str, Any]) -> None:
    exporter = InMemorySpanExporter()
    configure_tracing(world["settings"], extra_exporter=exporter)
    try:
        record = run(world, Scenario.COMPLETION)
    finally:
        shutdown_tracing()
    spans = exporter.get_finished_spans()
    names = [item.name for item in spans]
    assert names[-1] == "research.run"
    for expected in (
        "snapshot.freeze",
        "stage.researching",
        "stage.critiquing",
        "stage.synthesizing",
        "validation",
        "run.persist",
    ):
        assert expected in names, expected
    assert len({item.context.trace_id for item in spans}) == 1
    root = spans[-1]
    assert root.attributes is not None
    assert root.attributes["episalpha.state"] == "RESEARCH_COMPLETED"
    assert root.attributes["session.id"] == "run-0001"
    validation = next(item for item in spans if item.name == "validation")
    assert validation.attributes is not None
    assert validation.attributes["openinference.span.kind"] == "EVALUATOR"
    assert len(validation.events) == len(record.validation_report.checks)


def test_the_database_has_no_leftover_lease_after_a_run(world: dict[str, Any]) -> None:
    run(world, Scenario.COMPLETION)
    connection: sqlite3.Connection = world["repo"].connection
    assert connection.execute("SELECT COUNT(*) FROM run_lease").fetchone()[0] == 0


def test_proposals_and_records_are_artifacts(world: dict[str, Any]) -> None:
    run(world, Scenario.COMPLETION)
    artifacts = RunArtifacts(world["tmp"] / "runs", "run-0001")
    records = artifacts.read("records")
    assert [c["claim_id"] for c in records["claims"]] == ["run-0001.c1", "run-0001.c2"]
    assert artifacts.read("proposals") == []
    assert json.loads((artifacts.directory / "manifest.json").read_text())["snapshot_id"]
