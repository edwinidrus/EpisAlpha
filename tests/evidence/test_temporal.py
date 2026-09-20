"""M1-T03 — temporal eligibility, including the revision-selection fixture from the plan."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from episalpha.contracts.knowledge import AvailabilityBasis, EvidenceDocument
from episalpha.contracts.research import ResearchMode
from episalpha.evidence.temporal import (
    eligibility_time,
    eligible_documents,
    is_eligible,
    is_prior_record_available,
    select_current_versions,
)

T1 = datetime(2026, 2, 10, 21, 0, tzinfo=UTC)  # version A becomes public
T2 = datetime(2026, 2, 20, 12, 0, tzinfo=UTC)  # a research cutoff between the two versions
T3 = datetime(2026, 3, 5, 9, 0, tzinfo=UTC)  # corrected version B becomes public
TODAY = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)

HISTORICAL = ResearchMode.HISTORICAL_RECONSTRUCTION
FORWARD = ResearchMode.FORWARD_RESEARCH


def document(document_id: str, **overrides: Any) -> EvidenceDocument:
    base: dict[str, Any] = {
        "document_id": document_id,
        "source_uri": f"https://example.invalid/{document_id}",
        "source_type": "company_release",
        "source_family_id": "synthetic-release-family",
        "payload_hash": "a" * 64,
        "parsed_text_hash": "b" * 64,
        "parser_version": "test-parser-0",
        "published_at": T1,
        "public_available_at": T1,
        "availability_basis": AvailabilityBasis.PROVIDER_VERIFIED,
        "ingested_at": TODAY,
    }
    base.update(overrides)
    return EvidenceDocument(**base)


VERSION_A = document("synthetic-doc.v1", public_available_at=T1, published_at=T1)
VERSION_B = document(
    "synthetic-doc.v2",
    public_available_at=T3,
    published_at=T3,
    revises_document_id="synthetic-doc.v1",
)


# --- the plan's key fixture -------------------------------------------------------------------


def test_a_t2_query_returns_version_a_even_after_b_is_ingested() -> None:
    """Version A available at T1, corrected version B at T3; a T2 query must still see A."""
    selected = select_current_versions([VERSION_A, VERSION_B], T2, HISTORICAL)

    assert [d.document_id for d in selected] == ["synthetic-doc.v1"]


def test_a_query_after_t3_returns_the_correction() -> None:
    selected = select_current_versions([VERSION_A, VERSION_B], T3, HISTORICAL)

    assert [d.document_id for d in selected] == ["synthetic-doc.v2"]


def test_the_superseded_version_is_retained_not_deleted() -> None:
    """Rule 6: older versions stay; selection is a query, not a destructive update."""
    assert VERSION_A in eligible_documents([VERSION_A, VERSION_B], T3, HISTORICAL)


# --- boundaries -------------------------------------------------------------------------------


def test_a_version_available_exactly_at_the_cutoff_is_eligible() -> None:
    assert is_eligible(VERSION_A, T1, HISTORICAL) is True


def test_a_future_document_is_not_eligible() -> None:
    assert is_eligible(VERSION_B, T2, HISTORICAL) is False


# --- unverified availability ------------------------------------------------------------------


def test_a_publication_date_alone_does_not_qualify_a_version() -> None:
    """Rule 3: the printed date is not proof that today's fetched version existed then."""
    unverified = document(
        "synthetic-doc.unverified",
        published_at=T1,
        public_available_at=None,
        availability_basis=AvailabilityBasis.UNKNOWN,
    )

    assert eligibility_time(unverified) is None
    assert is_eligible(unverified, T2, HISTORICAL) is False


def test_first_capture_falls_back_to_our_own_capture_time() -> None:
    """Rule 2: conservative by construction, so it cannot reach back before the capture."""
    captured = document(
        "synthetic-doc.captured",
        published_at=T1,
        public_available_at=TODAY,
        ingested_at=TODAY,
        availability_basis=AvailabilityBasis.FIRST_CAPTURE,
    )

    assert eligibility_time(captured) == TODAY
    assert is_eligible(captured, T2, HISTORICAL) is False
    assert is_eligible(captured, TODAY, HISTORICAL) is True


def test_archive_verification_qualifies_a_historical_version() -> None:
    archived = document(
        "synthetic-doc.archived",
        public_available_at=T1,
        availability_basis=AvailabilityBasis.ARCHIVE_VERIFIED,
    )

    assert is_eligible(archived, T2, HISTORICAL) is True


# --- forward research -------------------------------------------------------------------------


def test_forward_run_requires_actual_capture_before_the_cutoff() -> None:
    """Rule 5: a late arrival must not sneak into an already frozen forward snapshot."""
    late = document("synthetic-doc.late", public_available_at=T1, ingested_at=TODAY)

    assert is_eligible(late, T2, FORWARD) is False


def test_forward_run_accepts_a_document_captured_before_the_cutoff() -> None:
    held = document("synthetic-doc.held", public_available_at=T1, ingested_at=T1)

    assert is_eligible(held, T2, FORWARD) is True


def test_forward_run_tolerates_unresolved_availability_for_what_we_already_hold() -> None:
    """We captured it ourselves before freezing, so capture time is the evidence."""
    held = document(
        "synthetic-doc.held",
        public_available_at=None,
        availability_basis=AvailabilityBasis.UNKNOWN,
        ingested_at=T1,
    )

    assert is_eligible(held, T2, FORWARD) is True


def test_forward_run_rejects_a_version_published_after_the_cutoff() -> None:
    later = document("synthetic-doc.later", public_available_at=T3, ingested_at=T1)

    assert is_eligible(later, T2, FORWARD) is False


# --- prior outputs are hindsight ----------------------------------------------------------------


def test_a_claim_written_today_is_not_available_to_a_past_cutoff() -> None:
    """Rule 8 and 9 together: creation time is never backdated to match the evidence."""
    assert is_prior_record_available(TODAY, T2) is False


def test_a_record_created_before_the_cutoff_is_available() -> None:
    assert is_prior_record_available(T1, T2) is True


def test_a_record_created_exactly_at_the_cutoff_is_available() -> None:
    assert is_prior_record_available(T2, T2) is True


# --- selection details ---------------------------------------------------------------------------


def test_families_are_selected_independently() -> None:
    other = document("other-doc.v1", source_family_id="other-family", public_available_at=T1)

    selected = select_current_versions([VERSION_A, VERSION_B, other], T3, HISTORICAL)

    # Ordered by source family so the result is stable across runs.
    assert [d.document_id for d in selected] == ["other-doc.v1", "synthetic-doc.v2"]


def test_nothing_qualifies_before_any_version_existed() -> None:
    assert (
        select_current_versions(
            [VERSION_A, VERSION_B], datetime(2026, 1, 1, tzinfo=UTC), HISTORICAL
        )
        == ()
    )


@pytest.mark.parametrize("mode", [HISTORICAL, FORWARD])
def test_selection_is_deterministic(mode: ResearchMode) -> None:
    forward_order = select_current_versions([VERSION_A, VERSION_B], T3, mode)
    reverse_order = select_current_versions([VERSION_B, VERSION_A], T3, mode)

    assert forward_order == reverse_order
