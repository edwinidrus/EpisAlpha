"""M4-T03 — replay is network-free and tamper-evident; recovery is explicit and keeps history."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fixtures.synthetic_knowledge import SYNTHETIC_DOCUMENT
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from research.test_runner import evidence, make_request

from episalpha.contracts.errors import EpisAlphaError, ErrorCode
from episalpha.contracts.knowledge import ReviewerType, SemanticAssessment, SemanticReviewStatus
from episalpha.contracts.research import RunState, RuntimeContext, StageResult
from episalpha.observability import configure_tracing, shutdown_tracing
from episalpha.research.artifacts import ArtifactIntegrityError, replay
from episalpha.research.runner import ResearchRunner, admit, claim, recover
from episalpha.runtime import model_relay
from episalpha.runtime.fake import FakeRuntime, Scenario
from episalpha.settings import Settings
from episalpha.storage.db import open_database
from episalpha.storage.objects import ObjectStore
from episalpha.storage.repository import Repository

NOW = datetime(2026, 10, 11, 8, 0, tzinfo=UTC)


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
        "runs": tmp_path / "runs",
    }
    connection.close()


def runner(world: dict[str, Any]) -> ResearchRunner:
    return ResearchRunner(
        world["repo"],
        world["objects"],
        world["settings"],
        evidence,
        artifacts_root=world["runs"],
        now=lambda: NOW,
    )


def completed_run(world: dict[str, Any]) -> str:
    request = make_request()
    admit(world["repo"], request, now=NOW)
    claim(world["repo"], request.run_id, "worker-1", now=NOW)
    record = runner(world).execute(
        request.run_id, FakeRuntime(world["objects"], Scenario.COMPLETION, now=lambda: NOW)
    )
    assert record.state is RunState.RESEARCH_COMPLETED
    return request.run_id


def test_replay_makes_no_calls_and_shows_the_saved_run(
    world: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    run_id = completed_run(world)

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("replay constructed or called a provider or runtime")

    monkeypatch.setattr(model_relay.ModelRelay, "__init__", forbidden)
    monkeypatch.setattr(model_relay.HttpTransport, "__call__", forbidden)
    monkeypatch.setattr(FakeRuntime, "run_stage", forbidden)
    exporter = InMemorySpanExporter()
    configure_tracing(world["settings"], extra_exporter=exporter)
    try:
        view = replay(world["repo"], world["runs"], run_id)
    finally:
        shutdown_tracing()

    assert view.record.state is RunState.RESEARCH_COMPLETED
    assert view.thesis is not None and view.thesis["thesis_id"] == f"{run_id}.thesis"
    assert view.manifest["snapshot_id"] == f"snapshot.{run_id}"
    assert [stage["result"]["stage"] for stage in view.stages] == [
        "RESEARCHING",
        "CRITIQUING",
        "SYNTHESIZING",
    ]
    assert view.verified == len(view.index["artifacts"])
    names = {item.name for item in exporter.get_finished_spans()}
    assert "replay" in names
    assert not any(name == "model.call" or name.startswith("connector.") for name in names)


def test_later_evidence_and_assessments_do_not_change_the_replay(world: dict[str, Any]) -> None:
    run_id = completed_run(world)
    before = replay(world["repo"], world["runs"], run_id)
    repo: Repository = world["repo"]
    repo.save_document(SYNTHETIC_DOCUMENT.model_copy(update={"document_id": "later-doc.v2"}))
    repo.save_assessment(
        SemanticAssessment(
            assessment_id="assessment.later",
            subject_id=f"{run_id}.c1",
            judgment=SemanticReviewStatus.SUPPORTED,
            reviewer_type=ReviewerType.HUMAN,
            reviewer_identity="owner",
            rationale="Checked by hand later.",
            assessed_at=NOW,
        )
    )
    after = replay(world["repo"], world["runs"], run_id)
    assert after.records == before.records
    assert after.thesis == before.thesis
    assert after.manifest == before.manifest


def test_flipping_one_byte_is_an_integrity_error(world: dict[str, Any]) -> None:
    run_id = completed_run(world)
    target = world["runs"] / run_id / "thesis.json"
    data = bytearray(target.read_bytes())
    data[10] ^= 0x01
    target.write_bytes(bytes(data))
    with pytest.raises(ArtifactIntegrityError) as raised:
        replay(world["repo"], world["runs"], run_id)
    assert raised.value.code is ErrorCode.INTEGRITY_ERROR


def test_a_consistent_edit_of_artifact_and_index_is_still_caught(world: dict[str, Any]) -> None:
    import hashlib
    import json

    run_id = completed_run(world)
    directory = world["runs"] / run_id
    thesis = json.loads((directory / "thesis.json").read_text())
    thesis["stance"] = "investigate" if thesis["stance"] != "investigate" else "abstain"
    data = json.dumps(thesis, sort_keys=True, separators=(",", ":")).encode()
    (directory / "thesis.json").write_bytes(data)
    index = json.loads((directory / "index.json").read_text())
    index["artifacts"]["thesis"] = hashlib.sha256(data).hexdigest()
    (directory / "index.json").write_text(json.dumps(index))
    with pytest.raises(ArtifactIntegrityError, match="canonical"):
        replay(world["repo"], world["runs"], run_id)


def test_unknown_run_is_refused(world: dict[str, Any]) -> None:
    with pytest.raises(EpisAlphaError) as raised:
        replay(world["repo"], world["runs"], "run-nothere")
    assert raised.value.code is ErrorCode.INVALID_REQUEST


class CrashingRuntime(FakeRuntime):
    """Completes the researcher, then 'crashes' mid model call in the critic stage."""

    def run_stage(self, stage: RunState, context: RuntimeContext) -> StageResult:
        if stage is RunState.CRITIQUING:
            raise SystemExit("process killed mid model call")
        return super().run_stage(stage, context)


def test_a_crash_stays_visible_and_recovery_is_a_new_attempt(world: dict[str, Any]) -> None:
    repo: Repository = world["repo"]
    request = make_request()
    admit(repo, request, now=NOW)
    claim(repo, request.run_id, "worker-1", now=NOW)
    with pytest.raises(SystemExit):
        runner(world).execute(
            request.run_id, CrashingRuntime(world["objects"], Scenario.COMPLETION, now=lambda: NOW)
        )
    crashed = repo.get_run(request.run_id)
    assert crashed is not None and crashed.state is RunState.CRITIQUING
    history = [(s.stage, s.completed, s.exit_reason) for s in repo.stage_results(request.run_id)]
    assert history == [
        (RunState.RESEARCHING, True, "completed"),
        (RunState.CRITIQUING, False, "started"),
    ]

    fake = FakeRuntime(world["objects"], Scenario.COMPLETION, now=lambda: NOW)
    calls: list[RunState] = []
    original = fake.run_stage

    def counting(stage: RunState, context: RuntimeContext) -> StageResult:
        calls.append(stage)
        return original(stage, context)

    fake.run_stage = counting  # type: ignore[method-assign]
    record = recover(repo, runner(world), request.run_id, fake, worker_id="worker-2", now=NOW)

    assert record.state is RunState.RESEARCH_COMPLETED, record.reason
    assert calls == [RunState.CRITIQUING, RunState.SYNTHESIZING]  # researcher was reused
    attempts = [(s.stage, s.completed) for s in repo.stage_results(request.run_id)]
    assert (RunState.CRITIQUING, False) in attempts  # the interrupted attempt is kept
    assert attempts.count((RunState.CRITIQUING, True)) == 1
    assert any("recovered" in warning for warning in record.warnings)


def test_recovering_a_finished_run_is_refused(world: dict[str, Any]) -> None:
    run_id = completed_run(world)
    fake = FakeRuntime(world["objects"], Scenario.COMPLETION, now=lambda: NOW)
    with pytest.raises(EpisAlphaError) as raised:
        recover(world["repo"], runner(world), run_id, fake, worker_id="worker-2", now=NOW)
    assert raised.value.code is ErrorCode.INVALID_REQUEST
