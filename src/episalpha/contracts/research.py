"""Research contracts and the run lifecycle (plan sections 3.2, 3.3, 3.6).

The knowledge contracts are imported, never redefined. A thesis is rendered from its
assertions; there is deliberately no free-text summary field that could bypass them.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from episalpha.contracts.errors import ErrorCode, InvalidTransitionError
from episalpha.contracts.knowledge import (
    ContentHash,
    Contract,
    Identifier,
    UtcTimestamp,
)

RETROSPECTIVE_NOTICE = "Retrospective research; model training knowledge may include later events."
"""Plan section 3.5. Point-in-time retrieval does not remove model-weight hindsight."""


class ResearchStance(StrEnum):
    INVESTIGATE = "investigate"
    WATCH = "watch"
    ABSTAIN = "abstain"


class ThesisSection(StrEnum):
    OBSERVATION = "observation"
    INTERPRETATION = "interpretation"
    EXPECTATION = "expectation"
    VARIANT_VIEW = "variant_view"
    TRANSMISSION = "transmission"
    BULL_CASE = "bull_case"
    BEAR_CASE = "bear_case"
    INVALIDATION = "invalidation"


class ResearchMode(StrEnum):
    FORWARD_RESEARCH = "forward_research"
    HISTORICAL_RECONSTRUCTION = "historical_reconstruction"


class RuntimeMode(StrEnum):
    FAKE = "fake"
    HERMES = "hermes"


class RunState(StrEnum):
    QUEUED = "QUEUED"
    SNAPSHOT_FROZEN = "SNAPSHOT_FROZEN"
    RESEARCHING = "RESEARCHING"
    CRITIQUING = "CRITIQUING"
    SYNTHESIZING = "SYNTHESIZING"
    VALIDATING = "VALIDATING"
    RESEARCH_COMPLETED = "RESEARCH_COMPLETED"
    ABSTAINED = "ABSTAINED"
    PARTIAL = "PARTIAL"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"


TERMINAL_STATES: frozenset[RunState] = frozenset(
    {
        RunState.RESEARCH_COMPLETED,
        RunState.ABSTAINED,
        RunState.PARTIAL,
        RunState.REJECTED,
        RunState.FAILED,
        RunState.CANCELLED,
        RunState.TIMED_OUT,
    }
)

ACTIVE_RESEARCH_STATES: frozenset[RunState] = frozenset(
    {RunState.RESEARCHING, RunState.CRITIQUING, RunState.SYNTHESIZING}
)

_INTERRUPTIONS: frozenset[RunState] = frozenset(
    {RunState.FAILED, RunState.CANCELLED, RunState.TIMED_OUT}
)

_ALLOWED: dict[RunState, frozenset[RunState]] = {
    RunState.QUEUED: frozenset({RunState.SNAPSHOT_FROZEN}),
    # Missing essential evidence is discovered at freeze time and abstains immediately.
    RunState.SNAPSHOT_FROZEN: frozenset({RunState.RESEARCHING, RunState.ABSTAINED}),
    RunState.RESEARCHING: frozenset({RunState.CRITIQUING, RunState.VALIDATING}),
    RunState.CRITIQUING: frozenset({RunState.SYNTHESIZING, RunState.VALIDATING}),
    RunState.SYNTHESIZING: frozenset({RunState.VALIDATING}),
    RunState.VALIDATING: frozenset(
        {
            RunState.RESEARCH_COMPLETED,
            RunState.ABSTAINED,
            RunState.PARTIAL,
            RunState.REJECTED,
        }
    ),
}


def allowed_transitions(state: RunState) -> frozenset[RunState]:
    """Every state a run may legally move to from ``state``."""
    if state in TERMINAL_STATES:
        return frozenset()
    return _ALLOWED.get(state, frozenset()) | _INTERRUPTIONS


def check_transition(current: RunState, proposed: RunState) -> None:
    """Raise :class:`InvalidTransitionError` unless the move is allowed."""
    if proposed not in allowed_transitions(current):
        reason = "terminal" if current in TERMINAL_STATES else "not an allowed successor"
        raise InvalidTransitionError(
            f"{current.value} -> {proposed.value} is rejected ({reason}); "
            f"allowed: {sorted(s.value for s in allowed_transitions(current))}"
        )


class Budgets(Contract):
    """The per-run slice of the settings limits, captured so a replay shows what applied."""

    run_wall_time_seconds: int = Field(gt=0)
    max_model_requests: int = Field(gt=0)
    max_tool_calls: int = Field(gt=0)
    max_output_tokens_per_call: int = Field(gt=0)


class RunRequest(Contract):
    """An admitted research request. ``idempotency_key`` makes re-submission safe."""

    run_id: Identifier
    idempotency_key: Identifier
    instrument_id: Identifier
    question: str = Field(min_length=1)
    research_cutoff: UtcTimestamp
    research_mode: ResearchMode
    runtime_mode: RuntimeMode
    harness_id: Identifier
    budgets: Budgets
    requested_at: UtcTimestamp


class SourceCompleteness(Contract):
    """What each source actually contributed to a snapshot.

    A snapshot that silently lacks a source is indistinguishable from one where that source had
    nothing to say. Recording the attempt separately from the outcome keeps "we could not look"
    apart from "there was nothing there" (plan M2-T04).
    """

    source_id: Identifier
    attempted: bool
    succeeded: bool
    document_count: int = Field(default=0, ge=0)
    failure_reason: str = ""

    @model_validator(mode="after")
    def _outcome_is_coherent(self) -> Self:
        if self.succeeded and not self.attempted:
            raise ValueError("a source cannot succeed without being attempted")
        if not self.succeeded and self.attempted and not self.failure_reason:
            raise ValueError("a failed source attempt must say why")
        if not self.succeeded and self.document_count:
            raise ValueError("a source that did not succeed contributed no documents")
        return self


class SnapshotManifest(Contract):
    """The immutable input set for a run. Nothing outside it is visible to the worker."""

    snapshot_id: Identifier
    snapshot_hash: ContentHash
    instrument_ids: tuple[Identifier, ...] = Field(min_length=1)
    research_cutoff: UtcTimestamp
    document_ids: tuple[Identifier, ...] = ()
    permitted_span_ids: tuple[Identifier, ...] = ()
    permitted_claim_ids: tuple[Identifier, ...] = ()
    permitted_relation_ids: tuple[Identifier, ...] = ()
    market_context_hash: ContentHash | None = None
    # Additive since schema version 1, defaulted so manifests written before it still validate.
    source_completeness: tuple[SourceCompleteness, ...] = ()
    source_version: str = Field(min_length=1)
    ontology_version: int
    frozen_at: UtcTimestamp


class ThesisAssertion(Contract):
    """The only way a material statement reaches a user.

    Every assertion must point at a claim or a hypothesis. An assertion that references neither
    is an unsourced opinion, which this product does not render.
    """

    assertion_id: Identifier
    section: ThesisSection
    text: str = Field(min_length=1)
    claim_ids: tuple[Identifier, ...] = ()
    hypothesis_ids: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def _must_reference_something(self) -> Self:
        if not self.claim_ids and not self.hypothesis_ids:
            raise ValueError(
                f"assertion {self.assertion_id!r} references no claim or hypothesis; material "
                "statements are never free text (plan section 3.2)"
            )
        return self


class Thesis(Contract):
    """The research output. Narrative sections are rendered from ``assertions``."""

    thesis_id: Identifier
    run_id: Identifier
    instrument_id: Identifier
    research_cutoff: UtcTimestamp
    research_mode: ResearchMode
    horizon_trading_days: int = Field(gt=0)
    stance: ResearchStance
    assertions: tuple[ThesisAssertion, ...] = Field(min_length=1)
    missing_information: tuple[str, ...] = ()
    next_inquiry: str = Field(min_length=1)
    snapshot_id: Identifier
    snapshot_hash: ContentHash
    harness_id: Identifier
    model_identifier: str = Field(min_length=1)
    created_at: UtcTimestamp

    @model_validator(mode="after")
    def _assertion_ids_unique(self) -> Self:
        ids = [assertion.assertion_id for assertion in self.assertions]
        if len(set(ids)) != len(ids):
            raise ValueError("assertion_id values must be unique within a thesis")
        return self

    @property
    def limitation_notice(self) -> str | None:
        """The retrospective warning, when this run reconstructs the past."""
        if self.research_mode is ResearchMode.HISTORICAL_RECONSTRUCTION:
            return RETROSPECTIVE_NOTICE
        return None


class CheckResult(Contract):
    """One deterministic validation check."""

    check: str = Field(min_length=1)
    passed: bool
    detail: str = ""


class ValidationReport(Contract):
    """The deterministic verdict on a candidate. It never asserts semantic support."""

    run_id: Identifier
    structurally_valid: bool
    checks: tuple[CheckResult, ...] = ()
    unresolved_semantic_reviews: tuple[Identifier, ...] = ()
    warnings: tuple[str, ...] = ()
    disposition: RunState
    error_code: ErrorCode | None = None

    @model_validator(mode="after")
    def _disposition_is_terminal_and_explained(self) -> Self:
        if self.disposition not in TERMINAL_STATES:
            raise ValueError(f"{self.disposition.value} is not a terminal disposition")
        if self.structurally_valid and self.disposition is RunState.REJECTED:
            raise ValueError("a structurally valid candidate cannot be disposed as REJECTED")
        if not self.structurally_valid and self.disposition is RunState.RESEARCH_COMPLETED:
            raise ValueError("a structurally invalid candidate cannot be disposed as completed")
        if self.disposition is RunState.REJECTED and self.error_code is None:
            raise ValueError("a rejection must carry an error code")
        return self


class Usage(Contract):
    """Reported usage. Unknown stays unknown; it is never estimated into a number."""

    model_requests: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cost_eur: None = None
    """Always ``None`` in v0.1: no verified pricing exists (plan section 3.8, row A22)."""


class StageResult(Contract):
    """What one workflow stage produced, including how it ended."""

    stage: RunState
    completed: bool
    exit_reason: str = Field(min_length=1)
    candidate_payload_hash: ContentHash | None = None
    tool_event_hashes: tuple[ContentHash, ...] = ()
    usage: Usage = Usage()
    started_at: UtcTimestamp
    ended_at: UtcTimestamp

    @model_validator(mode="after")
    def _times_ordered(self) -> Self:
        if self.ended_at < self.started_at:
            raise ValueError("ended_at must not precede started_at")
        return self


class RunRecord(Contract):
    """The persisted life of one run. Terminal records must explain themselves."""

    request: RunRequest
    state: RunState
    stages: tuple[StageResult, ...] = ()
    snapshot_id: Identifier | None = None
    thesis_id: Identifier | None = None
    validation_report: ValidationReport | None = None
    warnings: tuple[str, ...] = ()
    error_code: ErrorCode | None = None
    reason: str = ""
    usage: Usage = Usage()
    started_at: UtcTimestamp
    ended_at: UtcTimestamp | None = None

    @model_validator(mode="after")
    def _terminal_records_are_explained(self) -> Self:
        terminal = self.state in TERMINAL_STATES
        if terminal and not self.reason:
            raise ValueError(f"terminal state {self.state.value} requires a reason")
        if terminal and self.ended_at is None:
            raise ValueError(f"terminal state {self.state.value} requires ended_at")
        if not terminal and self.ended_at is not None:
            raise ValueError("a non-terminal run has not ended")
        failure_states = {RunState.REJECTED, RunState.FAILED, RunState.TIMED_OUT}
        if self.state in failure_states and self.error_code is None:
            raise ValueError(f"terminal state {self.state.value} requires an error code")
        if self.state is RunState.ABSTAINED and self.error_code is ErrorCode.SOURCE_FAILED:
            raise ValueError(
                "a source failure is not an abstention; record SOURCE_FAILED with state FAILED "
                "so an outage is never presented as a considered decision"
            )
        if self.state is RunState.RESEARCH_COMPLETED and self.thesis_id is None:
            raise ValueError("a completed run must reference its thesis")
        return self

    def transition(self, proposed: RunState) -> RunState:
        """Validate a proposed move. Returns the new state; raises if it is not allowed."""
        check_transition(self.state, proposed)
        return proposed


class RuntimeContext(Contract):
    """What a stage may read. The worker cannot widen it by asking.

    ``validated_claim_ids`` holds current-run records the host has already validated and
    assigned canonical IDs; they are separate from the immutable snapshot on purpose.
    """

    run_id: Identifier
    snapshot: SnapshotManifest
    stage: RunState
    validated_claim_ids: tuple[Identifier, ...] = ()
    validated_hypothesis_ids: tuple[Identifier, ...] = ()
    remaining_model_requests: int = Field(ge=0)
    remaining_tool_calls: int = Field(ge=0)
    remaining_wall_time_seconds: int = Field(ge=0)

    @model_validator(mode="after")
    def _stage_is_an_active_stage(self) -> Self:
        if self.stage not in ACTIVE_RESEARCH_STATES:
            raise ValueError(
                f"{self.stage.value} is not a stage a worker runs in; expected one of "
                f"{sorted(s.value for s in ACTIVE_RESEARCH_STATES)}"
            )
        return self

    @property
    def research_cutoff(self) -> UtcTimestamp:
        """Cutoff comes from the frozen snapshot, never from an agent-supplied argument."""
        return self.snapshot.research_cutoff
