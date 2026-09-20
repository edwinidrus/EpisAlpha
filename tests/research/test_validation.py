"""M1-T04 — the structural validator, and the line it refuses to cross."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fixtures.synthetic_knowledge import (
    CONTRADICTING_CLAIM,
    DEMAND_SPAN,
    DOCUMENT_TEXT,
    REPORTED_CLAIM,
    REVENUE_SPAN,
    SYNTHETIC_DOCUMENT,
    SYNTHETIC_ENTITY,
    SYNTHETIC_HYPOTHESIS,
    SYNTHETIC_INSTRUMENT,
)

from episalpha.contracts.errors import ErrorCode
from episalpha.contracts.knowledge import (
    Claim,
    Derivation,
    EpistemicStatus,
    EvidenceSpan,
    Relation,
    RelationPredicate,
    SemanticAssessment,
    SemanticReviewStatus,
)
from episalpha.contracts.research import (
    ResearchMode,
    ResearchStance,
    RunState,
    Thesis,
    ThesisAssertion,
    ThesisSection,
)
from episalpha.research.validation import RecordSet, failed_checks, validate

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
HASH = "c" * 64


def base_records(**overrides: Any) -> RecordSet:
    defaults: dict[str, Any] = {
        "entities": [SYNTHETIC_ENTITY],
        "instruments": [SYNTHETIC_INSTRUMENT],
        "documents": [SYNTHETIC_DOCUMENT],
        "spans": [REVENUE_SPAN, DEMAND_SPAN],
        "claims": [REPORTED_CLAIM, CONTRADICTING_CLAIM],
        "hypotheses": [SYNTHETIC_HYPOTHESIS],
        "document_texts": {"synthetic-doc.v1": DOCUMENT_TEXT},
    }
    defaults.update(overrides)
    return RecordSet(**defaults)


def thesis(**overrides: Any) -> Thesis:
    base: dict[str, Any] = {
        "thesis_id": "thesis.0001",
        "run_id": "run.0001",
        "instrument_id": "synthetic-issuer.eq",
        "research_cutoff": NOW,
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


def relation(**overrides: Any) -> Relation:
    base: dict[str, Any] = {
        "relation_id": "relation.0001",
        "predicate": RelationPredicate.REPORTS,
        "source_id": "synthetic-span.revenue",
        "target_id": "synthetic-claim.revenue",
        "epistemic_status": EpistemicStatus.REPORTED,
        "created_at": NOW,
    }
    base.update(overrides)
    return Relation(**base)


# --- the happy path -----------------------------------------------------------------------


def test_a_well_formed_candidate_passes() -> None:
    report = validate(base_records(relations=[relation()]), run_id="run.0001", thesis=thesis())

    assert report.structurally_valid is True
    assert report.disposition is RunState.RESEARCH_COMPLETED
    assert report.error_code is None


def test_partial_work_is_never_reported_as_complete() -> None:
    report = validate(base_records(), run_id="run.0001", partial=True)

    assert report.structurally_valid is True
    assert report.disposition is RunState.PARTIAL


# --- citations ----------------------------------------------------------------------------


def test_a_claim_citing_an_unknown_span_is_rejected() -> None:
    fabricated = Claim(
        claim_id="synthetic-claim.fabricated",
        statement="An invented figure.",
        subject_ids=("synthetic-issuer.eq",),
        attribution="invented",
        epistemic_status=EpistemicStatus.REPORTED,
        span_ids=("synthetic-span.nonexistent",),
        created_at=NOW,
    )

    report = validate(base_records(claims=[fabricated], hypotheses=[]), run_id="run.0001")

    assert report.disposition is RunState.REJECTED
    assert report.error_code is ErrorCode.INVALID_OUTPUT
    assert "cites unknown spans" in failed_checks(report)[0].detail


def test_a_quote_that_does_not_match_the_stored_text_is_rejected() -> None:
    width = REVENUE_SPAN.end_offset - REVENUE_SPAN.start_offset
    forged = EvidenceSpan(
        span_id="synthetic-span.forged",
        document_id="synthetic-doc.v1",
        start_offset=0,
        end_offset=width,
        exact_quote="Fourth quarter revenue reached EUR 999.0 million.".ljust(width, "."),
    )

    report = validate(base_records(spans=[forged], claims=[], hypotheses=[]), run_id="run.0001")

    assert report.structurally_valid is False
    assert "stored text reads" in failed_checks(report)[0].detail


def test_offsets_past_the_end_of_the_document_are_rejected() -> None:
    overrun = EvidenceSpan(
        span_id="synthetic-span.overrun",
        document_id="synthetic-doc.v1",
        start_offset=0,
        end_offset=5000,
        exact_quote="x" * 5000,
    )

    report = validate(base_records(spans=[overrun], claims=[], hypotheses=[]), run_id="run.0001")

    assert "offsets exceed" in failed_checks(report)[0].detail


def test_a_missing_document_text_is_reported_not_silently_passed() -> None:
    report = validate(base_records(document_texts={}, claims=[], hypotheses=[]), run_id="run.0001")

    assert report.structurally_valid is False
    assert "quotation unverifiable" in failed_checks(report)[0].detail


# --- relations ----------------------------------------------------------------------------


def test_a_relation_with_an_unresolvable_endpoint_is_rejected() -> None:
    report = validate(
        base_records(relations=[relation(target_id="claim.ghost")]), run_id="run.0001"
    )

    assert "does not resolve" in failed_checks(report)[0].detail


def test_a_relation_with_a_disallowed_endpoint_kind_is_rejected() -> None:
    """SUPPORTS runs claim -> hypothesis; a span may not support anything."""
    report = validate(
        base_records(
            relations=[
                relation(
                    relation_id="relation.bad",
                    predicate=RelationPredicate.SUPPORTS,
                    source_id="synthetic-span.revenue",
                    target_id="synthetic-hypothesis.demand",
                )
            ]
        ),
        run_id="run.0001",
    )

    assert "does not allow" in failed_checks(report)[0].detail


def test_a_span_cannot_report_a_hypothesised_claim() -> None:
    """An unsupported mechanism must not be relabelled as something a source stated."""
    mechanism = Claim(
        claim_id="synthetic-claim.mechanism",
        statement="Guidance drives the order book.",
        subject_ids=("synthetic-issuer.eq",),
        attribution="analyst mechanism",
        epistemic_status=EpistemicStatus.HYPOTHESIZED,
        created_at=NOW,
    )

    report = validate(
        base_records(
            claims=[mechanism],
            hypotheses=[],
            relations=[relation(target_id="synthetic-claim.mechanism")],
        ),
        run_id="run.0001",
    )

    assert "cannot REPORT a hypothesised claim" in failed_checks(report)[0].detail


# --- derivations ---------------------------------------------------------------------------


def derived(**overrides: Any) -> Claim:
    base: dict[str, Any] = {
        "claim_id": "synthetic-claim.derived",
        "statement": "Revenue grew year over year.",
        "subject_ids": ("synthetic-issuer.eq",),
        "attribution": "EpisAlpha derivation",
        "epistemic_status": EpistemicStatus.DERIVED,
        "derivation": Derivation(
            method="year_over_year_growth",
            method_version="1",
            input_claim_ids=("synthetic-claim.revenue",),
        ),
        "created_at": NOW,
    }
    base.update(overrides)
    return Claim(**base)


def test_a_derivation_from_an_unknown_input_is_rejected() -> None:
    orphan = derived(
        derivation=Derivation(
            method="m", method_version="1", input_claim_ids=("synthetic-claim.ghost",)
        )
    )

    report = validate(base_records(claims=[orphan], hypotheses=[]), run_id="run.0001")

    assert "derives from unknown claims" in failed_checks(report)[0].detail


def test_a_claim_cannot_derive_from_itself() -> None:
    circular = derived(
        derivation=Derivation(
            method="m", method_version="1", input_claim_ids=("synthetic-claim.derived",)
        )
    )

    report = validate(base_records(claims=[circular], hypotheses=[]), run_id="run.0001")

    assert "cannot derive from itself" in failed_checks(report)[0].detail


# --- the semantic boundary -------------------------------------------------------------------


def test_clean_citations_do_not_make_a_claim_supported() -> None:
    """The whole point: a string match is not entailment."""
    report = validate(base_records(), run_id="run.0001")

    assert report.structurally_valid is True
    assert set(report.unresolved_semantic_reviews) == {
        "synthetic-claim.revenue",
        "synthetic-claim.demand",
    }
    assert "remain unreviewed" in report.warnings[0]


def test_claiming_support_without_an_assessment_is_rejected() -> None:
    asserted = REPORTED_CLAIM.model_copy(
        update={"semantic_review_status": SemanticReviewStatus.SUPPORTED}
    )

    report = validate(base_records(claims=[asserted, CONTRADICTING_CLAIM]), run_id="run.0001")

    assert "no recorded assessment" in failed_checks(report)[0].detail


def test_a_recorded_assessment_makes_the_status_legitimate() -> None:
    asserted = REPORTED_CLAIM.model_copy(
        update={"semantic_review_status": SemanticReviewStatus.SUPPORTED}
    )
    assessment = SemanticAssessment(
        assessment_id="assessment.0001",
        subject_id="synthetic-claim.revenue",
        judgment=SemanticReviewStatus.SUPPORTED,
        rationale="The passage states the figure verbatim.",
        reviewer_type="human",
        reviewer_identity="owner",
        assessed_at=NOW,
    )

    report = validate(
        base_records(claims=[asserted, CONTRADICTING_CLAIM], assessments=[assessment]),
        run_id="run.0001",
    )

    assert report.structurally_valid is True
    # The assessed claim leaves the unreviewed list; the unassessed one stays on it.
    assert "synthetic-claim.revenue" not in report.unresolved_semantic_reviews
    assert "synthetic-claim.demand" in report.unresolved_semantic_reviews


def test_a_status_that_contradicts_its_assessment_is_rejected() -> None:
    asserted = REPORTED_CLAIM.model_copy(
        update={"semantic_review_status": SemanticReviewStatus.SUPPORTED}
    )
    assessment = SemanticAssessment(
        assessment_id="assessment.0001",
        subject_id="synthetic-claim.revenue",
        judgment=SemanticReviewStatus.UNSUPPORTED,
        rationale="The passage does not state this.",
        reviewer_type="human",
        reviewer_identity="owner",
        assessed_at=NOW,
    )

    report = validate(
        base_records(claims=[asserted, CONTRADICTING_CLAIM], assessments=[assessment]),
        run_id="run.0001",
    )

    assert "but the current assessment says" in failed_checks(report)[0].detail


def test_a_superseded_assessment_does_not_win() -> None:
    """Assessments are versioned; the current one governs, history is kept."""
    asserted = REPORTED_CLAIM.model_copy(
        update={"semantic_review_status": SemanticReviewStatus.UNSUPPORTED}
    )
    original = SemanticAssessment(
        assessment_id="assessment.0001",
        subject_id="synthetic-claim.revenue",
        judgment=SemanticReviewStatus.SUPPORTED,
        rationale="Initial reading.",
        reviewer_type="human",
        reviewer_identity="owner",
        assessed_at=NOW,
    )
    revision = SemanticAssessment(
        assessment_id="assessment.0002",
        subject_id="synthetic-claim.revenue",
        judgment=SemanticReviewStatus.UNSUPPORTED,
        rationale="On review, the figure is not stated in this passage.",
        reviewer_type="human",
        reviewer_identity="owner",
        assessed_at=NOW,
        supersedes_assessment_id="assessment.0001",
    )

    report = validate(
        base_records(claims=[asserted, CONTRADICTING_CLAIM], assessments=[original, revision]),
        run_id="run.0001",
    )

    assert report.structurally_valid is True


# --- thesis coverage ---------------------------------------------------------------------------


def test_an_assertion_referencing_an_unknown_claim_is_rejected() -> None:
    bad = thesis(
        assertions=(
            ThesisAssertion(
                assertion_id="assertion.0001",
                section=ThesisSection.INTERPRETATION,
                text="An unsupported statement.",
                claim_ids=("synthetic-claim.ghost",),
            ),
        )
    )

    report = validate(base_records(), run_id="run.0001", thesis=bad)

    assert "references unknown records" in failed_checks(report)[0].detail


def test_a_hypothesis_referencing_an_unknown_claim_is_rejected() -> None:
    orphan = SYNTHETIC_HYPOTHESIS.model_copy(
        update={"supporting_claim_ids": ("synthetic-claim.ghost",)}
    )

    report = validate(base_records(hypotheses=[orphan]), run_id="run.0001")

    assert "references unknown claims" in failed_checks(report)[0].detail


@pytest.mark.parametrize("partial", [False, True])
def test_an_invalid_candidate_is_rejected_regardless_of_partial(partial: bool) -> None:
    report = validate(
        base_records(relations=[relation(target_id="claim.ghost")]),
        run_id="run.0001",
        partial=partial,
    )

    assert report.disposition is RunState.REJECTED
