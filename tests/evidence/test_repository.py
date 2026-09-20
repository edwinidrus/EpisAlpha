"""M2-T01 — persistence, migrations, transactions, and referential integrity."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fixtures.synthetic_knowledge import (
    CONTRADICTING_CLAIM,
    DEMAND_SPAN,
    REPORTED_CLAIM,
    REVENUE_SPAN,
    SYNTHETIC_DOCUMENT,
    SYNTHETIC_ENTITY,
    SYNTHETIC_HYPOTHESIS,
    SYNTHETIC_INSTRUMENT,
)

from episalpha.contracts.knowledge import (
    EpistemicStatus,
    RecordKind,
    Relation,
    RelationPredicate,
    SemanticAssessment,
    SemanticReviewStatus,
)
from episalpha.contracts.research import (
    Budgets,
    ResearchMode,
    ResearchStance,
    RunRecord,
    RunRequest,
    RunState,
    RuntimeMode,
    SnapshotManifest,
    StageResult,
    Thesis,
    ThesisAssertion,
    ThesisSection,
    Usage,
)
from episalpha.storage.db import connect, migrate, open_database, schema_version, transaction
from episalpha.storage.repository import IntegrityError, Repository

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
CUTOFF = datetime(2026, 2, 28, 22, 0, tzinfo=UTC)
HASH = "c" * 64


@pytest.fixture
def connection(tmp_path: Path) -> sqlite3.Connection:
    return open_database(tmp_path / "app.sqlite3")


@pytest.fixture
def repo(connection: sqlite3.Connection) -> Repository:
    return Repository(connection)


@pytest.fixture
def seeded(connection: sqlite3.Connection, repo: Repository) -> Repository:
    """A database holding the synthetic entity, instrument, document, spans and claims."""
    with transaction(connection):
        repo.save_all(
            [
                SYNTHETIC_ENTITY,
                SYNTHETIC_INSTRUMENT,
                SYNTHETIC_DOCUMENT,
                REVENUE_SPAN,
                DEMAND_SPAN,
                REPORTED_CLAIM,
                CONTRADICTING_CLAIM,
                SYNTHETIC_HYPOTHESIS,
            ]
        )
    return repo


def run_record(**overrides: Any) -> RunRecord:
    request = RunRequest(
        run_id=overrides.pop("run_id", "run.0001"),
        idempotency_key=overrides.pop("idempotency_key", "idem.0001"),
        instrument_id="synthetic-issuer.eq",
        question="Did guidance change?",
        research_cutoff=CUTOFF,
        research_mode=ResearchMode.FORWARD_RESEARCH,
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
    base: dict[str, Any] = {"request": request, "state": RunState.QUEUED, "started_at": NOW}
    base.update(overrides)
    return RunRecord(**base)


def thesis(**overrides: Any) -> Thesis:
    base: dict[str, Any] = {
        "thesis_id": "thesis.0001",
        "run_id": "run.0001",
        "instrument_id": "synthetic-issuer.eq",
        "research_cutoff": CUTOFF,
        "research_mode": ResearchMode.FORWARD_RESEARCH,
        "horizon_trading_days": 20,
        "stance": ResearchStance.WATCH,
        "assertions": (
            ThesisAssertion(
                assertion_id="assertion.0001",
                section=ThesisSection.OBSERVATION,
                text="Revenue was reported at EUR 412.0 million.",
                claim_ids=("synthetic-claim.revenue",),
            ),
        ),
        "next_inquiry": "Check the next filing.",
        "snapshot_id": "snapshot.0001",
        "snapshot_hash": HASH,
        "harness_id": "harness.baseline",
        "model_identifier": "glm-5.3",
        "created_at": NOW,
    }
    base.update(overrides)
    return Thesis(**base)


def snapshot(**overrides: Any) -> SnapshotManifest:
    base: dict[str, Any] = {
        "snapshot_id": "snapshot.0001",
        "snapshot_hash": HASH,
        "instrument_ids": ("synthetic-issuer.eq",),
        "research_cutoff": CUTOFF,
        "source_version": "test-sources-0",
        "ontology_version": 1,
        "frozen_at": NOW,
    }
    base.update(overrides)
    return SnapshotManifest(**base)


# --- migration -----------------------------------------------------------------------------


def test_migration_creates_the_schema_on_an_empty_database(tmp_path: Path) -> None:
    connection = connect(tmp_path / "fresh.sqlite3")

    assert schema_version(connection) == 0
    assert migrate(connection) == 1

    tables = {
        row["name"]
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    assert {"node", "evidence_document", "relation", "run", "stage_result"} <= tables


def test_migration_is_idempotent(connection: sqlite3.Connection) -> None:
    assert migrate(connection) == 1
    assert migrate(connection) == 1


def test_connection_enforces_foreign_keys_and_wal(connection: sqlite3.Connection) -> None:
    assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert connection.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"


# --- round trips ----------------------------------------------------------------------------


def test_records_round_trip_through_their_contracts(seeded: Repository) -> None:
    assert seeded.get_entity("synthetic-issuer") == SYNTHETIC_ENTITY
    assert seeded.get_document("synthetic-doc.v1") == SYNTHETIC_DOCUMENT
    assert seeded.get_span("synthetic-span.revenue") == REVENUE_SPAN
    assert seeded.get_claim("synthetic-claim.revenue") == REPORTED_CLAIM
    assert seeded.get_hypothesis("synthetic-hypothesis.demand") == SYNTHETIC_HYPOTHESIS


def test_node_kinds_are_registered(seeded: Repository) -> None:
    assert seeded.node_kind("synthetic-issuer") is RecordKind.ENTITY
    assert seeded.node_kind("synthetic-span.revenue") is RecordKind.EVIDENCE_SPAN
    assert seeded.node_kind("nothing-here") is None


def test_one_id_cannot_be_two_kinds(seeded: Repository, connection: sqlite3.Connection) -> None:
    clash = SYNTHETIC_HYPOTHESIS.model_copy(update={"hypothesis_id": "synthetic-issuer"})

    with pytest.raises(IntegrityError, match="already registered"), transaction(connection):
        seeded.save_hypothesis(clash)


# --- relationship endpoints cannot dangle -----------------------------------------------------


def test_a_relation_between_registered_nodes_is_stored(
    seeded: Repository, connection: sqlite3.Connection
) -> None:
    relation = Relation(
        relation_id="relation.0001",
        predicate=RelationPredicate.REPORTS,
        source_id="synthetic-span.revenue",
        target_id="synthetic-claim.revenue",
        epistemic_status=EpistemicStatus.REPORTED,
        created_at=NOW,
    )

    with transaction(connection):
        seeded.save_relation(relation)

    assert seeded.relations_from("synthetic-span.revenue") == (relation,)


def test_a_relation_to_an_unregistered_node_is_refused_by_the_database(
    seeded: Repository, connection: sqlite3.Connection
) -> None:
    """SQLite itself rejects the edge; this is not an application-level check."""
    dangling = Relation(
        relation_id="relation.ghost",
        predicate=RelationPredicate.REPORTS,
        source_id="synthetic-span.revenue",
        target_id="synthetic-claim.ghost",
        epistemic_status=EpistemicStatus.REPORTED,
        created_at=NOW,
    )

    with pytest.raises(sqlite3.IntegrityError), transaction(connection):
        seeded.save_relation(dangling)


def test_a_span_for_an_unknown_document_is_refused(
    repo: Repository, connection: sqlite3.Connection
) -> None:
    with pytest.raises(sqlite3.IntegrityError), transaction(connection):
        repo.save_span(REVENUE_SPAN)


# --- transactions ------------------------------------------------------------------------------


def test_rollback_leaves_no_half_written_thesis(
    seeded: Repository, connection: sqlite3.Connection
) -> None:
    """The plan's acceptance case: a failure mid-write must persist nothing."""
    with pytest.raises(sqlite3.IntegrityError):
        with transaction(connection):
            seeded.save_thesis(thesis())
            seeded.save_relation(
                Relation(
                    relation_id="relation.bad",
                    predicate=RelationPredicate.SUPPORTS,
                    source_id="synthetic-claim.revenue",
                    target_id="hypothesis.ghost",
                    epistemic_status=EpistemicStatus.REPORTED,
                    created_at=NOW,
                )
            )

    assert seeded.get_thesis("thesis.0001") is None


def test_nested_transactions_are_refused(connection: sqlite3.Connection) -> None:
    """A nested block would commit the outer work early — exactly the half-write we forbid."""
    with transaction(connection), pytest.raises(RuntimeError, match="already open"):  # noqa: SIM117
        with transaction(connection):
            pass


# --- document versions ---------------------------------------------------------------------------


def test_a_document_version_cannot_be_rewritten_in_place(
    seeded: Repository, connection: sqlite3.Connection
) -> None:
    altered = SYNTHETIC_DOCUMENT.model_copy(update={"payload_hash": "f" * 64})

    with pytest.raises(IntegrityError, match="different content"), transaction(connection):
        seeded.save_document(altered)


def test_saving_the_identical_document_again_is_allowed(
    seeded: Repository, connection: sqlite3.Connection
) -> None:
    with transaction(connection):
        seeded.save_document(SYNTHETIC_DOCUMENT)

    assert seeded.get_document("synthetic-doc.v1") == SYNTHETIC_DOCUMENT


def test_both_versions_of_a_family_are_retained(
    seeded: Repository, connection: sqlite3.Connection
) -> None:
    revision = SYNTHETIC_DOCUMENT.model_copy(
        update={
            "document_id": "synthetic-doc.v2",
            "ingested_at": SYNTHETIC_DOCUMENT.ingested_at + timedelta(days=20),
            "revises_document_id": "synthetic-doc.v1",
        }
    )

    with transaction(connection):
        seeded.save_document(revision)

    family = seeded.documents_in_family("synthetic-release-family")
    assert [d.document_id for d in family] == ["synthetic-doc.v1", "synthetic-doc.v2"]


# --- versioned assessments ------------------------------------------------------------------------


def assessment(**overrides: Any) -> SemanticAssessment:
    base: dict[str, Any] = {
        "assessment_id": "assessment.0001",
        "subject_id": "synthetic-claim.revenue",
        "judgment": SemanticReviewStatus.SUPPORTED,
        "rationale": "The passage states the figure verbatim.",
        "reviewer_type": "human",
        "reviewer_identity": "owner",
        "assessed_at": NOW,
    }
    base.update(overrides)
    return SemanticAssessment(**base)


def test_superseding_an_assessment_keeps_the_original(
    seeded: Repository, connection: sqlite3.Connection
) -> None:
    original = assessment()
    revision = assessment(
        assessment_id="assessment.0002",
        judgment=SemanticReviewStatus.UNSUPPORTED,
        rationale="On review the figure is not stated in this passage.",
        assessed_at=NOW + timedelta(hours=1),
        supersedes_assessment_id="assessment.0001",
    )

    with transaction(connection):
        seeded.save_assessment(original)
        seeded.save_assessment(revision)

    assert seeded.assessments_for("synthetic-claim.revenue") == (original, revision)
    current = seeded.current_assessment("synthetic-claim.revenue")
    assert current is not None
    assert current.assessment_id == "assessment.0002"


def test_no_assessment_means_no_current_judgment(seeded: Repository) -> None:
    assert seeded.current_assessment("synthetic-claim.revenue") is None


# --- runs and idempotency -------------------------------------------------------------------------


def test_duplicate_idempotency_keys_do_not_create_a_second_run(
    seeded: Repository, connection: sqlite3.Connection
) -> None:
    """Re-submitting a request must not spend the model budget twice."""
    first = run_record()
    with transaction(connection):
        admitted = seeded.admit_run(first)
    with transaction(connection):
        again = seeded.admit_run(run_record(run_id="run.0002"))

    assert admitted.request.run_id == "run.0001"
    assert again.request.run_id == "run.0001"
    assert connection.execute("SELECT COUNT(*) FROM run").fetchone()[0] == 1


def test_a_different_key_admits_a_new_run(
    seeded: Repository, connection: sqlite3.Connection
) -> None:
    with transaction(connection):
        seeded.admit_run(run_record())
    with transaction(connection):
        seeded.admit_run(run_record(run_id="run.0002", idempotency_key="idem.0002"))

    assert connection.execute("SELECT COUNT(*) FROM run").fetchone()[0] == 2


def test_updating_an_unadmitted_run_is_refused(
    seeded: Repository, connection: sqlite3.Connection
) -> None:
    with pytest.raises(IntegrityError, match="has not been admitted"), transaction(connection):
        seeded.update_run(run_record())


def test_run_state_survives_a_round_trip(
    seeded: Repository, connection: sqlite3.Connection
) -> None:
    with transaction(connection):
        seeded.save_snapshot(snapshot())
        seeded.admit_run(run_record())
    finished = run_record(
        state=RunState.ABSTAINED,
        reason="no eligible evidence before the cutoff",
        ended_at=NOW + timedelta(minutes=2),
        snapshot_id="snapshot.0001",
    )
    with transaction(connection):
        seeded.update_run(finished)

    stored = seeded.get_run("run.0001")
    assert stored is not None
    assert stored.state is RunState.ABSTAINED
    assert seeded.runs_in_state(RunState.ABSTAINED) == (stored,)


# --- snapshots ------------------------------------------------------------------------------------


def test_a_frozen_snapshot_cannot_be_altered(
    seeded: Repository, connection: sqlite3.Connection
) -> None:
    with transaction(connection):
        seeded.save_snapshot(snapshot())

    with pytest.raises(IntegrityError, match="immutable"), transaction(connection):
        seeded.save_snapshot(snapshot(snapshot_hash="d" * 64))


# --- stage checkpoints and usage ------------------------------------------------------------------


def stage(**overrides: Any) -> StageResult:
    base: dict[str, Any] = {
        "stage": RunState.RESEARCHING,
        "completed": True,
        "exit_reason": "stage finished",
        "usage": Usage(model_requests=2, tool_calls=3, prompt_tokens=100, completion_tokens=50),
        "started_at": NOW,
        "ended_at": NOW + timedelta(seconds=30),
    }
    base.update(overrides)
    return StageResult(**base)


def test_an_incomplete_stage_is_kept_not_discarded(
    seeded: Repository, connection: sqlite3.Connection
) -> None:
    """Partial work must survive a failure, visibly incomplete."""
    with transaction(connection):
        seeded.admit_run(run_record())
        seeded.save_stage_result("run.0001", 1, stage())
        seeded.save_stage_result(
            "run.0001", 2, stage(completed=False, exit_reason="provider transport failure")
        )

    results = seeded.stage_results("run.0001")
    assert len(results) == 2
    assert [r.completed for r in results] == [True, False]


def test_usage_sums_across_attempts_and_cost_stays_unknown(
    seeded: Repository, connection: sqlite3.Connection
) -> None:
    with transaction(connection):
        seeded.admit_run(run_record())
        seeded.save_stage_result("run.0001", 1, stage())
        seeded.save_stage_result("run.0001", 2, stage(stage=RunState.CRITIQUING))

    usage = seeded.run_usage("run.0001")
    assert usage["model_requests"] == 4
    assert usage["tool_calls"] == 6
    assert usage["cost_eur"] is None


# --- full-text search -----------------------------------------------------------------------------


def test_spans_are_searchable(seeded: Repository) -> None:
    hits = seeded.search_spans("revenue", limit=6)

    assert [s.span_id for s in hits] == ["synthetic-span.revenue"]


def test_search_respects_the_limit(seeded: Repository) -> None:
    assert len(seeded.search_spans("the OR a OR demand OR revenue", limit=1)) == 1


def test_the_search_index_follows_a_rollback(
    seeded: Repository, connection: sqlite3.Connection
) -> None:
    """A rolled-back span must not stay findable; the index is inside the transaction."""
    rolled_back = REVENUE_SPAN.model_copy(
        update={
            "span_id": "synthetic-span.temporary",
            "exact_quote": "Zorbleflux" * 5,
            "start_offset": 0,
            "end_offset": 50,
        }
    )

    with pytest.raises(RuntimeError):
        with transaction(connection):
            seeded.save_span(rolled_back)
            raise RuntimeError("deliberate failure")

    assert seeded.search_spans("Zorbleflux", limit=6) == ()
