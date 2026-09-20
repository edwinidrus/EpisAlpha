"""M1-T02 — research contracts, run lifecycle, and error semantics."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic import ValidationError

from episalpha.contracts.errors import EpisAlphaError, ErrorCode, InvalidTransitionError
from episalpha.contracts.research import (
    ACTIVE_RESEARCH_STATES,
    RETROSPECTIVE_NOTICE,
    TERMINAL_STATES,
    Budgets,
    ResearchMode,
    ResearchStance,
    RunRecord,
    RunRequest,
    RunState,
    RuntimeContext,
    RuntimeMode,
    SnapshotManifest,
    StageResult,
    Thesis,
    ThesisAssertion,
    ThesisSection,
    Usage,
    ValidationReport,
    allowed_transitions,
    check_transition,
)

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
CUTOFF = datetime(2026, 2, 28, 22, 0, tzinfo=UTC)
HASH = "c" * 64


def request_kwargs(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "run_id": "run.0001",
        "idempotency_key": "idem.0001",
        "instrument_id": "synthetic-issuer.eq",
        "question": "Did guidance change?",
        "research_cutoff": CUTOFF,
        "research_mode": ResearchMode.FORWARD_RESEARCH,
        "runtime_mode": RuntimeMode.FAKE,
        "harness_id": "harness.baseline",
        "budgets": Budgets(
            run_wall_time_seconds=300,
            max_model_requests=8,
            max_tool_calls=12,
            max_output_tokens_per_call=4000,
        ),
        "requested_at": NOW,
    }
    base.update(overrides)
    return base


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


def assertion(**overrides: Any) -> ThesisAssertion:
    base: dict[str, Any] = {
        "assertion_id": "assertion.0001",
        "section": ThesisSection.OBSERVATION,
        "text": "The issuer reported synthetic revenue of EUR 412.0 million.",
        "claim_ids": ("synthetic-claim.revenue",),
    }
    base.update(overrides)
    return ThesisAssertion(**base)


def thesis_kwargs(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "thesis_id": "thesis.0001",
        "run_id": "run.0001",
        "instrument_id": "synthetic-issuer.eq",
        "research_cutoff": CUTOFF,
        "research_mode": ResearchMode.FORWARD_RESEARCH,
        "horizon_trading_days": 20,
        "stance": ResearchStance.WATCH,
        "assertions": (assertion(),),
        "next_inquiry": "Confirm the order book with the next filing.",
        "snapshot_id": "snapshot.0001",
        "snapshot_hash": HASH,
        "harness_id": "harness.baseline",
        "model_identifier": "glm-5.3",
        "created_at": NOW,
    }
    base.update(overrides)
    return base


def record_kwargs(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "request": RunRequest(**request_kwargs()),
        "state": RunState.QUEUED,
        "started_at": NOW,
    }
    base.update(overrides)
    return base


# --- lifecycle ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("current", "proposed"),
    [
        (RunState.QUEUED, RunState.SNAPSHOT_FROZEN),
        (RunState.SNAPSHOT_FROZEN, RunState.RESEARCHING),
        (RunState.SNAPSHOT_FROZEN, RunState.ABSTAINED),
        (RunState.RESEARCHING, RunState.CRITIQUING),
        (RunState.RESEARCHING, RunState.VALIDATING),
        (RunState.CRITIQUING, RunState.SYNTHESIZING),
        (RunState.SYNTHESIZING, RunState.VALIDATING),
        (RunState.VALIDATING, RunState.RESEARCH_COMPLETED),
        (RunState.VALIDATING, RunState.PARTIAL),
        (RunState.VALIDATING, RunState.REJECTED),
    ],
)
def test_allowed_transition(current: RunState, proposed: RunState) -> None:
    check_transition(current, proposed)


@pytest.mark.parametrize(
    ("current", "proposed"),
    [
        (RunState.QUEUED, RunState.RESEARCHING),
        (RunState.QUEUED, RunState.RESEARCH_COMPLETED),
        (RunState.SNAPSHOT_FROZEN, RunState.SYNTHESIZING),
        (RunState.RESEARCHING, RunState.RESEARCH_COMPLETED),
        (RunState.VALIDATING, RunState.RESEARCHING),
    ],
)
def test_rejected_transition(current: RunState, proposed: RunState) -> None:
    with pytest.raises(InvalidTransitionError, match="rejected"):
        check_transition(current, proposed)


@pytest.mark.parametrize("state", sorted(TERMINAL_STATES, key=lambda s: s.value))
def test_terminal_states_have_no_successors(state: RunState) -> None:
    assert allowed_transitions(state) == frozenset()


@pytest.mark.parametrize("state", sorted(ACTIVE_RESEARCH_STATES, key=lambda s: s.value))
def test_any_active_stage_can_be_interrupted(state: RunState) -> None:
    for interruption in (RunState.FAILED, RunState.CANCELLED, RunState.TIMED_OUT):
        check_transition(state, interruption)


def test_invalid_transition_carries_the_frozen_error_code() -> None:
    with pytest.raises(EpisAlphaError) as caught:
        check_transition(RunState.QUEUED, RunState.RESEARCH_COMPLETED)

    assert caught.value.code is ErrorCode.INVALID_REQUEST


def test_record_transition_helper_uses_the_same_rules() -> None:
    record = RunRecord(**record_kwargs())

    assert record.transition(RunState.SNAPSHOT_FROZEN) is RunState.SNAPSHOT_FROZEN
    with pytest.raises(InvalidTransitionError):
        record.transition(RunState.VALIDATING)


# --- assertions are the only route to a user ------------------------------------------------


def test_assertion_without_references_rejected() -> None:
    with pytest.raises(ValidationError, match="never free text"):
        assertion(claim_ids=(), hypothesis_ids=())


def test_assertion_backed_by_a_hypothesis_alone_is_allowed() -> None:
    assert assertion(claim_ids=(), hypothesis_ids=("synthetic-hypothesis.demand",))


def test_thesis_has_no_free_text_summary_field() -> None:
    assert "summary" not in Thesis.model_fields


def test_thesis_requires_at_least_one_assertion() -> None:
    with pytest.raises(ValidationError):
        Thesis(**thesis_kwargs(assertions=()))


def test_thesis_assertion_ids_must_be_unique() -> None:
    with pytest.raises(ValidationError, match="unique"):
        Thesis(**thesis_kwargs(assertions=(assertion(), assertion())))


def test_thesis_requires_a_next_inquiry() -> None:
    with pytest.raises(ValidationError):
        Thesis(**thesis_kwargs(next_inquiry=""))


# --- retrospective labelling ------------------------------------------------------------------


def test_historical_reconstruction_carries_the_limitation_notice() -> None:
    thesis = Thesis(**thesis_kwargs(research_mode=ResearchMode.HISTORICAL_RECONSTRUCTION))

    assert thesis.limitation_notice == RETROSPECTIVE_NOTICE
    assert "training knowledge" in RETROSPECTIVE_NOTICE


def test_forward_research_carries_no_notice() -> None:
    assert Thesis(**thesis_kwargs()).limitation_notice is None


# --- terminal records explain themselves --------------------------------------------------


@pytest.mark.parametrize("state", sorted(TERMINAL_STATES, key=lambda s: s.value))
def test_terminal_record_requires_a_reason(state: RunState) -> None:
    with pytest.raises(ValidationError, match="requires a reason"):
        RunRecord(**record_kwargs(state=state, ended_at=NOW, error_code=ErrorCode.NO_DATA))


def test_terminal_record_requires_an_end_time() -> None:
    with pytest.raises(ValidationError, match="requires ended_at"):
        RunRecord(**record_kwargs(state=RunState.ABSTAINED, reason="no eligible evidence"))


def test_non_terminal_record_cannot_have_ended() -> None:
    with pytest.raises(ValidationError, match="has not ended"):
        RunRecord(**record_kwargs(state=RunState.RESEARCHING, ended_at=NOW))


@pytest.mark.parametrize("state", [RunState.REJECTED, RunState.FAILED, RunState.TIMED_OUT])
def test_failure_states_require_an_error_code(state: RunState) -> None:
    with pytest.raises(ValidationError, match="requires an error code"):
        RunRecord(**record_kwargs(state=state, ended_at=NOW, reason="something went wrong"))


def test_abstention_is_not_a_source_failure() -> None:
    """A provider outage must never be presented as a considered abstention."""
    with pytest.raises(ValidationError, match="not an abstention"):
        RunRecord(
            **record_kwargs(
                state=RunState.ABSTAINED,
                ended_at=NOW,
                reason="provider unreachable",
                error_code=ErrorCode.SOURCE_FAILED,
            )
        )


def test_abstention_for_missing_information_is_allowed() -> None:
    record = RunRecord(
        **record_kwargs(
            state=RunState.ABSTAINED,
            ended_at=NOW,
            reason="no eligible evidence before the cutoff",
            error_code=ErrorCode.NO_DATA,
        )
    )

    assert record.error_code is ErrorCode.NO_DATA


def test_completed_run_must_reference_its_thesis() -> None:
    with pytest.raises(ValidationError, match="must reference its thesis"):
        RunRecord(
            **record_kwargs(state=RunState.RESEARCH_COMPLETED, ended_at=NOW, reason="completed")
        )


# --- validation reports ---------------------------------------------------------------------


def report_kwargs(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "run_id": "run.0001",
        "structurally_valid": True,
        "disposition": RunState.RESEARCH_COMPLETED,
    }
    base.update(overrides)
    return base


def test_report_disposition_must_be_terminal() -> None:
    with pytest.raises(ValidationError, match="not a terminal disposition"):
        ValidationReport(**report_kwargs(disposition=RunState.VALIDATING))


def test_valid_candidate_cannot_be_rejected() -> None:
    with pytest.raises(ValidationError, match="cannot be disposed as REJECTED"):
        ValidationReport(
            **report_kwargs(disposition=RunState.REJECTED, error_code=ErrorCode.INVALID_OUTPUT)
        )


def test_invalid_candidate_cannot_be_completed() -> None:
    with pytest.raises(ValidationError, match="cannot be disposed as completed"):
        ValidationReport(**report_kwargs(structurally_valid=False))


def test_rejection_requires_an_error_code() -> None:
    with pytest.raises(ValidationError, match="must carry an error code"):
        ValidationReport(**report_kwargs(structurally_valid=False, disposition=RunState.REJECTED))


# --- usage and runtime context ----------------------------------------------------------------


def test_cost_is_structurally_unknowable_in_v0_1() -> None:
    """Row A22: no fabricated EUR total. The field cannot hold a number at all."""
    assert Usage().cost_eur is None
    with pytest.raises(ValidationError):
        Usage(cost_eur="25.00")


def test_runtime_context_takes_its_cutoff_from_the_snapshot() -> None:
    context = RuntimeContext(
        run_id="run.0001",
        snapshot=snapshot(),
        stage=RunState.RESEARCHING,
        remaining_model_requests=8,
        remaining_tool_calls=12,
        remaining_wall_time_seconds=300,
    )

    assert context.research_cutoff == CUTOFF


def test_runtime_context_stage_must_be_a_worker_stage() -> None:
    with pytest.raises(ValidationError, match="not a stage a worker runs in"):
        RuntimeContext(
            run_id="run.0001",
            snapshot=snapshot(),
            stage=RunState.VALIDATING,
            remaining_model_requests=8,
            remaining_tool_calls=12,
            remaining_wall_time_seconds=300,
        )


def test_remaining_budget_cannot_go_negative() -> None:
    with pytest.raises(ValidationError):
        RuntimeContext(
            run_id="run.0001",
            snapshot=snapshot(),
            stage=RunState.RESEARCHING,
            remaining_model_requests=-1,
            remaining_tool_calls=12,
            remaining_wall_time_seconds=300,
        )


def test_stage_result_times_must_be_ordered() -> None:
    with pytest.raises(ValidationError, match="must not precede"):
        StageResult(
            stage=RunState.RESEARCHING,
            completed=False,
            exit_reason="interrupted",
            started_at=NOW,
            ended_at=NOW - timedelta(seconds=1),
        )


def test_incomplete_stage_still_records_its_reason_and_usage() -> None:
    """Network failure after partial work must preserve that work, visibly incomplete."""
    stage = StageResult(
        stage=RunState.RESEARCHING,
        completed=False,
        exit_reason="provider transport failure after 2 tool calls",
        usage=Usage(model_requests=2, tool_calls=2),
        started_at=NOW,
        ended_at=NOW + timedelta(seconds=30),
    )

    assert stage.completed is False
    assert stage.usage.tool_calls == 2
