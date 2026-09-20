"""Canonical knowledge contracts (plan sections 3.2-3.4), schema version 1.

These types are the frozen vocabulary of what EpisAlpha believes and why. They enforce the
structural rules only. Whether a claim is *semantically* supported by its passage is a separate
judgment recorded in :class:`SemanticAssessment`; nothing here may infer it.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Annotated, Any, Self

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

SCHEMA_VERSION = 1

_IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9_.-]{2,63}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class EpistemicStatus(StrEnum):
    """How a claim came to be known. Plan section 3.3."""

    REPORTED = "reported"
    DERIVED = "derived"
    HYPOTHESIZED = "hypothesized"


class SemanticReviewStatus(StrEnum):
    """Whether a reviewer judged the claim to follow from its evidence. Plan section 3.3."""

    UNREVIEWED = "unreviewed"
    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    UNSUPPORTED = "unsupported"


class RelationPredicate(StrEnum):
    """The seven allowed edges. Plan section 3.4. There is no CAUSES in v0.1."""

    ISSUED_BY = "ISSUED_BY"
    HAS_SPAN = "HAS_SPAN"
    REPORTS = "REPORTS"
    ABOUT = "ABOUT"
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    DERIVED_FROM = "DERIVED_FROM"


class AvailabilityBasis(StrEnum):
    """How confident we are about when a document version became public. Plan section 3.5."""

    PROVIDER_VERIFIED = "provider_verified"
    ARCHIVE_VERIFIED = "archive_verified"
    FIRST_CAPTURE = "first_capture"
    UNKNOWN = "unknown"


class ReviewerType(StrEnum):
    """Who supplied a semantic judgment."""

    HUMAN = "human"
    SECONDARY_MODEL = "secondary_model"


class RecordKind(StrEnum):
    """Node kinds, used to validate relation endpoints."""

    ENTITY = "entity"
    INSTRUMENT = "instrument"
    EVIDENCE_DOCUMENT = "evidence_document"
    EVIDENCE_SPAN = "evidence_span"
    CLAIM = "claim"
    EVENT = "event"
    HYPOTHESIS = "hypothesis"
    THESIS = "thesis"


ALLOWED_ENDPOINTS: dict[RelationPredicate, tuple[frozenset[RecordKind], frozenset[RecordKind]]] = {
    RelationPredicate.ISSUED_BY: (
        frozenset({RecordKind.INSTRUMENT}),
        frozenset({RecordKind.ENTITY}),
    ),
    RelationPredicate.HAS_SPAN: (
        frozenset({RecordKind.EVIDENCE_DOCUMENT}),
        frozenset({RecordKind.EVIDENCE_SPAN}),
    ),
    RelationPredicate.REPORTS: (
        frozenset({RecordKind.EVIDENCE_SPAN}),
        frozenset({RecordKind.CLAIM}),
    ),
    RelationPredicate.ABOUT: (
        frozenset({RecordKind.CLAIM}),
        frozenset({RecordKind.ENTITY, RecordKind.INSTRUMENT, RecordKind.EVENT}),
    ),
    RelationPredicate.SUPPORTS: (
        frozenset({RecordKind.CLAIM}),
        frozenset({RecordKind.HYPOTHESIS, RecordKind.THESIS}),
    ),
    RelationPredicate.CONTRADICTS: (
        frozenset({RecordKind.CLAIM}),
        frozenset({RecordKind.CLAIM, RecordKind.HYPOTHESIS, RecordKind.THESIS}),
    ),
    RelationPredicate.DERIVED_FROM: (
        frozenset({RecordKind.THESIS}),
        frozenset({RecordKind.THESIS}),
    ),
}
"""Plan section 3.4. Used by the validator; unknown predicates cannot reach here at all."""


def _identifier(value: Any) -> Any:
    if isinstance(value, str) and not _IDENTIFIER.match(value):
        raise ValueError(
            f"{value!r} is not a valid identifier: 3-64 characters, starting with a lowercase "
            "letter or digit, then lowercase letters, digits, underscore, dot or dash. "
            "Identifiers are application-generated and filesystem-safe; user titles and model "
            "text are never identifiers"
        )
    return value


def _aware_utc(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError(
                f"{value!r} is naive; all timestamps are timezone-aware UTC with an explicit "
                "offset (plan section 3.2)"
            )
        return value.astimezone(UTC)
    return value


def _decimal_string(value: Any) -> Any:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool) or not isinstance(value, str):
        raise ValueError(
            'financial values must be quoted decimal strings such as "1234.50", never binary '
            "floating-point numbers (plan section 3.2)"
        )
    try:
        return Decimal(value)
    except InvalidOperation:
        raise ValueError(f"{value!r} is not a decimal number") from None


def _content_hash(value: Any) -> Any:
    if isinstance(value, str) and not _HEX64.match(value):
        raise ValueError(f"{value!r} must be a lowercase 64-character SHA-256 hex digest")
    return value


Identifier = Annotated[str, BeforeValidator(_identifier)]
UtcTimestamp = Annotated[datetime, BeforeValidator(_aware_utc)]
DecimalString = Annotated[Decimal, BeforeValidator(_decimal_string)]
ContentHash = Annotated[str, BeforeValidator(_content_hash)]


class Contract(BaseModel):
    """Base for every canonical record: closed, immutable, explicit."""

    model_config = ConfigDict(extra="forbid", frozen=True, protected_namespaces=())


class Entity(Contract):
    """A legal or economic actor."""

    entity_id: Identifier
    kind: str
    canonical_name: str = Field(min_length=1)
    aliases: tuple[str, ...] = ()
    external_identifiers: dict[str, str] = Field(default_factory=dict)


class TickerAlias(Contract):
    """A ticker is only true for a period; ticker changes must not break instrument identity."""

    ticker: str = Field(min_length=1)
    valid_from: UtcTimestamp
    valid_to: UtcTimestamp | None = None

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.valid_to is not None and self.valid_to <= self.valid_from:
            raise ValueError("valid_to must be after valid_from")
        return self


class Instrument(Contract):
    """A tradable instrument, whose canonical identity survives ticker changes."""

    instrument_id: Identifier
    issuer_entity_id: Identifier
    exchange: str = Field(min_length=1)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    ticker_aliases: tuple[TickerAlias, ...] = ()


class EvidenceDocument(Contract):
    """One *version* of one source document. Later revisions never overwrite earlier ones."""

    document_id: Identifier
    source_uri: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    source_family_id: Identifier
    payload_hash: ContentHash
    parsed_text_hash: ContentHash
    parser_version: str = Field(min_length=1)
    published_at: UtcTimestamp | None = None
    public_available_at: UtcTimestamp | None = None
    availability_basis: AvailabilityBasis
    ingested_at: UtcTimestamp
    revises_document_id: Identifier | None = None

    @model_validator(mode="after")
    def _availability_is_consistent(self) -> Self:
        verified = {AvailabilityBasis.PROVIDER_VERIFIED, AvailabilityBasis.ARCHIVE_VERIFIED}
        if self.availability_basis in verified and self.public_available_at is None:
            raise ValueError(
                f"availability_basis {self.availability_basis.value!r} asserts a verified public "
                "availability time, so public_available_at is required"
            )
        if self.availability_basis is AvailabilityBasis.FIRST_CAPTURE and (
            self.public_available_at is not None and self.public_available_at != self.ingested_at
        ):
            raise ValueError(
                "availability_basis 'first_capture' means the capture time is the conservative "
                "eligibility time; public_available_at must equal ingested_at or be omitted"
            )
        if self.revises_document_id == self.document_id:
            raise ValueError("a document cannot revise itself")
        return self


class EvidenceSpan(Contract):
    """An exact passage of a document's normalized text."""

    span_id: Identifier
    document_id: Identifier
    start_offset: int = Field(ge=0)
    end_offset: int = Field(ge=0)
    exact_quote: str = Field(min_length=1)
    section_locator: str | None = None

    @model_validator(mode="after")
    def _offsets_match_quote(self) -> Self:
        if self.end_offset <= self.start_offset:
            raise ValueError(
                f"end_offset ({self.end_offset}) must be greater than start_offset "
                f"({self.start_offset})"
            )
        width = self.end_offset - self.start_offset
        if len(self.exact_quote) != width:
            raise ValueError(
                f"exact_quote is {len(self.exact_quote)} characters but the span covers {width}; "
                "offsets and quote must describe the same passage"
            )
        return self


class NumericFact(Contract):
    """A measured quantity. Every dimension is required: a missing one is never guessed."""

    metric: str = Field(min_length=1)
    value: DecimalString
    unit: str = Field(min_length=1)
    period_start: UtcTimestamp
    period_end: UtcTimestamp
    accounting_basis: str = Field(min_length=1)
    source_context: str = Field(min_length=1)

    @model_validator(mode="after")
    def _period_ordered(self) -> Self:
        if self.period_end < self.period_start:
            raise ValueError("period_end must not precede period_start")
        return self


class Derivation(Contract):
    """A deterministic computation, reproducible from its inputs and method version."""

    method: str = Field(min_length=1)
    method_version: str = Field(min_length=1)
    input_claim_ids: tuple[Identifier, ...] = Field(min_length=1)


class Claim(Contract):
    """One atomic statement, with its provenance.

    ``semantic_review_status`` stays ``unreviewed`` here by construction. Only a recorded
    :class:`SemanticAssessment` may change it, and the validator enforces that.
    """

    claim_id: Identifier
    statement: str = Field(min_length=1)
    subject_ids: tuple[Identifier, ...] = Field(min_length=1)
    attribution: str = Field(min_length=1)
    epistemic_status: EpistemicStatus
    span_ids: tuple[Identifier, ...] = ()
    derivation: Derivation | None = None
    numeric_fact: NumericFact | None = None
    semantic_review_status: SemanticReviewStatus = SemanticReviewStatus.UNREVIEWED
    created_at: UtcTimestamp
    run_id: Identifier | None = None

    @model_validator(mode="after")
    def _provenance_matches_status(self) -> Self:
        if self.epistemic_status is EpistemicStatus.REPORTED and not self.span_ids:
            raise ValueError(
                "a 'reported' claim must cite at least one evidence span: it asserts that a "
                "source said this"
            )
        if self.epistemic_status is EpistemicStatus.DERIVED and self.derivation is None:
            raise ValueError(
                "a 'derived' claim must carry a derivation naming its inputs and method version"
            )
        if self.epistemic_status is EpistemicStatus.HYPOTHESIZED and (
            self.span_ids or self.derivation is not None
        ):
            raise ValueError(
                "a 'hypothesized' claim carries neither spans nor a derivation; state the "
                "mechanism and assumptions on a Hypothesis instead"
            )
        return self


class Event(Contract):
    """Something that happened in economic time, supported by claims."""

    event_id: Identifier
    event_type: str = Field(min_length=1)
    participant_entity_ids: tuple[Identifier, ...] = Field(min_length=1)
    occurred_at: UtcTimestamp
    period_end: UtcTimestamp | None = None
    supporting_claim_ids: tuple[Identifier, ...] = Field(min_length=1)


class Hypothesis(Contract):
    """A proposed mechanism. It never becomes a fact by repetition."""

    hypothesis_id: Identifier
    mechanism: str = Field(min_length=1)
    assumptions: tuple[str, ...] = Field(min_length=1)
    supporting_claim_ids: tuple[Identifier, ...] = ()
    opposing_claim_ids: tuple[Identifier, ...] = ()
    falsification_condition: str = Field(min_length=1)
    horizon_trading_days: int = Field(gt=0)
    created_at: UtcTimestamp

    @model_validator(mode="after")
    def _claims_are_disjoint(self) -> Self:
        overlap = set(self.supporting_claim_ids) & set(self.opposing_claim_ids)
        if overlap:
            raise ValueError(f"claims cannot both support and oppose: {sorted(overlap)}")
        return self


class Relation(Contract):
    """A typed edge. Endpoint *kinds* are checked by the validator, which can resolve IDs."""

    relation_id: Identifier
    predicate: RelationPredicate
    source_id: Identifier
    target_id: Identifier
    evidence_span_ids: tuple[Identifier, ...] = ()
    derivation: Derivation | None = None
    epistemic_status: EpistemicStatus
    valid_from: UtcTimestamp | None = None
    valid_to: UtcTimestamp | None = None
    created_at: UtcTimestamp
    run_id: Identifier | None = None

    @model_validator(mode="after")
    def _endpoints_differ(self) -> Self:
        if self.source_id == self.target_id:
            raise ValueError(f"self-relation on {self.source_id!r} is not allowed")
        if self.valid_to is not None and self.valid_from is not None:
            if self.valid_to <= self.valid_from:
                raise ValueError("valid_to must be after valid_from")
        return self


class SemanticAssessment(Contract):
    """A recorded judgment. Assessments are versioned; they never overwrite history."""

    assessment_id: Identifier
    subject_id: Identifier
    judgment: SemanticReviewStatus
    rationale: str = Field(min_length=1)
    reviewer_type: ReviewerType
    reviewer_identity: str = Field(min_length=1)
    assessed_at: UtcTimestamp
    supersedes_assessment_id: Identifier | None = None

    @model_validator(mode="after")
    def _judgment_is_a_decision(self) -> Self:
        if self.judgment is SemanticReviewStatus.UNREVIEWED:
            raise ValueError(
                "an assessment records a decision; 'unreviewed' is the absence of one, so do "
                "not store it as an assessment"
            )
        if self.supersedes_assessment_id == self.assessment_id:
            raise ValueError("an assessment cannot supersede itself")
        return self
