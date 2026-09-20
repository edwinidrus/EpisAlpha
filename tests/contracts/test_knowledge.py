"""M1-T01 — knowledge contracts reject malformed and under-specified records."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from fixtures.synthetic_knowledge import (
    CONTRADICTING_CLAIM,
    DEMAND_SPAN,
    DOCUMENT_TEXT,
    REPORTED_CLAIM,
    REVENUE_SPAN,
    SYNTHETIC_DOCUMENT,
    SYNTHETIC_HYPOTHESIS,
)
from pydantic import ValidationError

from episalpha.contracts.knowledge import (
    ALLOWED_ENDPOINTS,
    AvailabilityBasis,
    Claim,
    Derivation,
    EpistemicStatus,
    EvidenceDocument,
    EvidenceSpan,
    Hypothesis,
    NumericFact,
    Relation,
    RelationPredicate,
    SemanticAssessment,
    SemanticReviewStatus,
)

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)


def document_kwargs(**overrides: Any) -> dict[str, Any]:
    base = SYNTHETIC_DOCUMENT.model_dump()
    base.update(overrides)
    return base


def claim_kwargs(**overrides: Any) -> dict[str, Any]:
    base = REPORTED_CLAIM.model_dump()
    base.pop("numeric_fact", None)
    base.update(overrides)
    return base


# --- the fixture itself is a contract test -------------------------------------------------


def test_fixture_spans_quote_the_document_exactly() -> None:
    for span in (REVENUE_SPAN, DEMAND_SPAN):
        assert DOCUMENT_TEXT[span.start_offset : span.end_offset] == span.exact_quote


def test_fixture_claims_are_unreviewed_by_default() -> None:
    assert REPORTED_CLAIM.semantic_review_status is SemanticReviewStatus.UNREVIEWED
    assert CONTRADICTING_CLAIM.semantic_review_status is SemanticReviewStatus.UNREVIEWED


# --- identifiers and timestamps ------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_id",
    ["Q4 Revenue Claim", "../escape", "ab", "UPPER", "trailing/slash", ""],
)
def test_malformed_identifier_rejected(bad_id: str) -> None:
    with pytest.raises(ValidationError, match="identifier|string_too"):
        Claim(**claim_kwargs(claim_id=bad_id))


def test_naive_timestamp_rejected() -> None:
    with pytest.raises(ValidationError, match="naive"):
        Claim(**claim_kwargs(created_at=datetime(2026, 9, 20, 12, 0)))  # noqa: DTZ001


def test_aware_non_utc_timestamp_is_normalised_not_rejected() -> None:
    from datetime import timedelta, timezone

    berlin = timezone(timedelta(hours=2))
    claim = Claim(**claim_kwargs(created_at=datetime(2026, 9, 20, 14, 0, tzinfo=berlin)))

    assert claim.created_at == NOW


def test_unsupported_status_rejected() -> None:
    with pytest.raises(ValidationError):
        Claim(**claim_kwargs(epistemic_status="rumoured"))


# --- claim provenance ----------------------------------------------------------------------


def test_reported_claim_without_span_rejected() -> None:
    with pytest.raises(ValidationError, match="must cite at least one evidence span"):
        Claim(**claim_kwargs(span_ids=()))


def test_derived_claim_without_derivation_rejected() -> None:
    with pytest.raises(ValidationError, match="must carry a derivation"):
        Claim(**claim_kwargs(epistemic_status=EpistemicStatus.DERIVED, span_ids=()))


def test_derived_claim_with_derivation_accepted() -> None:
    claim = Claim(
        **claim_kwargs(
            epistemic_status=EpistemicStatus.DERIVED,
            span_ids=(),
            derivation=Derivation(
                method="year_over_year_growth",
                method_version="1",
                input_claim_ids=("synthetic-claim.revenue",),
            ),
        )
    )

    assert claim.derivation is not None


def test_hypothesised_claim_cannot_borrow_evidence() -> None:
    with pytest.raises(ValidationError, match="neither spans nor a derivation"):
        Claim(**claim_kwargs(epistemic_status=EpistemicStatus.HYPOTHESIZED))


def test_derivation_requires_inputs() -> None:
    with pytest.raises(ValidationError):
        Derivation(method="m", method_version="1", input_claim_ids=())


# --- spans ---------------------------------------------------------------------------------


@pytest.mark.parametrize(("start", "end"), [(10, 10), (10, 5)])
def test_inverted_or_empty_span_rejected(start: int, end: int) -> None:
    with pytest.raises(ValidationError, match="greater than start_offset"):
        EvidenceSpan(
            span_id="synthetic-span.bad",
            document_id="synthetic-doc.v1",
            start_offset=start,
            end_offset=end,
            exact_quote="x",
        )


def test_span_quote_length_must_match_offsets() -> None:
    with pytest.raises(ValidationError, match="same passage"):
        EvidenceSpan(
            span_id="synthetic-span.bad",
            document_id="synthetic-doc.v1",
            start_offset=0,
            end_offset=10,
            exact_quote="short",
        )


# --- numeric facts -------------------------------------------------------------------------


def numeric_kwargs(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "metric": "revenue",
        "value": "412000000.00",
        "unit": "EUR",
        "period_start": datetime(2025, 10, 1, tzinfo=UTC),
        "period_end": datetime(2025, 12, 31, tzinfo=UTC),
        "accounting_basis": "IFRS consolidated",
        "source_context": "headline figure",
    }
    base.update(overrides)
    return base


@pytest.mark.parametrize(
    "missing", ["metric", "unit", "accounting_basis", "source_context", "period_start"]
)
def test_numeric_fact_requires_every_dimension(missing: str) -> None:
    kwargs = numeric_kwargs()
    del kwargs[missing]

    with pytest.raises(ValidationError, match=missing):
        NumericFact(**kwargs)


def test_numeric_value_must_be_a_decimal_string() -> None:
    with pytest.raises(ValidationError, match="quoted decimal strings"):
        NumericFact(**numeric_kwargs(value=412000000.00))


def test_numeric_value_preserves_written_precision() -> None:
    assert NumericFact(**numeric_kwargs(value="412000000.00")).value == Decimal("412000000.00")


def test_numeric_period_must_be_ordered() -> None:
    with pytest.raises(ValidationError, match="period_end must not precede"):
        NumericFact(
            **numeric_kwargs(
                period_start=datetime(2025, 12, 31, tzinfo=UTC),
                period_end=datetime(2025, 10, 1, tzinfo=UTC),
            )
        )


# --- documents and availability --------------------------------------------------------------


@pytest.mark.parametrize(
    "basis", [AvailabilityBasis.PROVIDER_VERIFIED, AvailabilityBasis.ARCHIVE_VERIFIED]
)
def test_verified_availability_requires_a_time(basis: AvailabilityBasis) -> None:
    with pytest.raises(ValidationError, match="public_available_at is required"):
        EvidenceDocument(**document_kwargs(availability_basis=basis, public_available_at=None))


def test_first_capture_cannot_claim_an_earlier_public_time() -> None:
    with pytest.raises(ValidationError, match="must equal ingested_at"):
        EvidenceDocument(
            **document_kwargs(
                availability_basis=AvailabilityBasis.FIRST_CAPTURE,
                public_available_at=datetime(2026, 1, 1, tzinfo=UTC),
            )
        )


def test_document_cannot_revise_itself() -> None:
    with pytest.raises(ValidationError, match="cannot revise itself"):
        EvidenceDocument(**document_kwargs(revises_document_id="synthetic-doc.v1"))


def test_content_hash_must_be_sha256_hex() -> None:
    with pytest.raises(ValidationError, match="64-character"):
        EvidenceDocument(**document_kwargs(payload_hash="not-a-hash"))


# --- hypotheses ----------------------------------------------------------------------------


def hypothesis_kwargs(**overrides: Any) -> dict[str, Any]:
    base = SYNTHETIC_HYPOTHESIS.model_dump()
    base.update(overrides)
    return base


@pytest.mark.parametrize("missing", ["assumptions", "falsification_condition"])
def test_hypothesis_requires_assumptions_and_falsifier(missing: str) -> None:
    empty: Any = () if missing == "assumptions" else ""

    with pytest.raises(ValidationError, match=missing):
        Hypothesis(**hypothesis_kwargs(**{missing: empty}))


def test_hypothesis_horizon_must_be_positive() -> None:
    with pytest.raises(ValidationError, match="horizon_trading_days"):
        Hypothesis(**hypothesis_kwargs(horizon_trading_days=0))


def test_claim_cannot_both_support_and_oppose() -> None:
    with pytest.raises(ValidationError, match="both support and oppose"):
        Hypothesis(
            **hypothesis_kwargs(
                supporting_claim_ids=("synthetic-claim.demand",),
                opposing_claim_ids=("synthetic-claim.demand",),
            )
        )


# --- relations -----------------------------------------------------------------------------


def relation_kwargs(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "relation_id": "synthetic-relation.reports",
        "predicate": RelationPredicate.REPORTS,
        "source_id": "synthetic-span.revenue",
        "target_id": "synthetic-claim.revenue",
        "epistemic_status": EpistemicStatus.REPORTED,
        "created_at": NOW,
    }
    base.update(overrides)
    return base


def test_unknown_predicate_rejected() -> None:
    with pytest.raises(ValidationError):
        Relation(**relation_kwargs(predicate="CAUSES"))


def test_self_relation_rejected() -> None:
    with pytest.raises(ValidationError, match="self-relation"):
        Relation(**relation_kwargs(target_id="synthetic-span.revenue"))


def test_every_predicate_has_declared_endpoints() -> None:
    assert set(ALLOWED_ENDPOINTS) == set(RelationPredicate)


# --- semantic assessments --------------------------------------------------------------------


def assessment_kwargs(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "assessment_id": "synthetic-assessment.1",
        "subject_id": "synthetic-claim.revenue",
        "judgment": SemanticReviewStatus.SUPPORTED,
        "rationale": "The quoted passage states the figure verbatim.",
        "reviewer_type": "human",
        "reviewer_identity": "owner",
        "assessed_at": NOW,
    }
    base.update(overrides)
    return base


def test_assessment_cannot_record_unreviewed() -> None:
    with pytest.raises(ValidationError, match="absence of one"):
        SemanticAssessment(**assessment_kwargs(judgment=SemanticReviewStatus.UNREVIEWED))


def test_assessment_requires_a_rationale_and_reviewer() -> None:
    with pytest.raises(ValidationError):
        SemanticAssessment(**assessment_kwargs(rationale=""))


def test_assessment_cannot_supersede_itself() -> None:
    with pytest.raises(ValidationError, match="supersede itself"):
        SemanticAssessment(**assessment_kwargs(supersedes_assessment_id="synthetic-assessment.1"))


# --- immutability ----------------------------------------------------------------------------


def test_records_are_frozen() -> None:
    with pytest.raises(ValidationError):
        REPORTED_CLAIM.statement = "rewritten"  # type: ignore[misc]


def test_unknown_field_rejected() -> None:
    with pytest.raises(ValidationError, match="confidence"):
        Claim(**claim_kwargs(confidence=0.9))
