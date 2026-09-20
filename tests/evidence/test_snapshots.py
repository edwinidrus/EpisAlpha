"""M2-T04 — frozen snapshots: immutability, closure, completeness, and cutoff behaviour."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from episalpha.contracts.knowledge import (
    AvailabilityBasis,
    Claim,
    EpistemicStatus,
    EvidenceDocument,
    EvidenceSpan,
    Relation,
    RelationPredicate,
)
from episalpha.contracts.research import ResearchMode, SourceCompleteness
from episalpha.evidence.snapshots import (
    NotInSnapshotError,
    build_snapshot,
    build_view,
    compute_snapshot_hash,
    verify_snapshot,
)

T1 = datetime(2026, 2, 10, 21, 0, tzinfo=UTC)
T2 = datetime(2026, 2, 20, 12, 0, tzinfo=UTC)
T3 = datetime(2026, 3, 5, 9, 0, tzinfo=UTC)
FROZEN_AT = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
HISTORICAL = ResearchMode.HISTORICAL_RECONSTRUCTION

TEXT_A = "Fourth quarter revenue reached EUR 412.0 million."
TEXT_B = "Fourth quarter revenue reached EUR 409.5 million, as corrected."


def document(document_id: str, available_at: datetime, **overrides: Any) -> EvidenceDocument:
    base: dict[str, Any] = {
        "document_id": document_id,
        "source_uri": f"https://example.invalid/{document_id}",
        "source_type": "company_release",
        "source_family_id": "release-family",
        "payload_hash": "a" * 64,
        "parsed_text_hash": "b" * 64,
        "parser_version": "test-parser-0",
        "published_at": available_at,
        "public_available_at": available_at,
        "availability_basis": AvailabilityBasis.PROVIDER_VERIFIED,
        "ingested_at": FROZEN_AT,
    }
    base.update(overrides)
    return EvidenceDocument(**base)


def span(span_id: str, document_id: str, text: str) -> EvidenceSpan:
    return EvidenceSpan(
        span_id=span_id,
        document_id=document_id,
        start_offset=0,
        end_offset=len(text),
        exact_quote=text,
    )


DOC_A = document("release.v1", T1)
DOC_B = document("release.v2", T3, revises_document_id="release.v1")
SPAN_A = span("span.v1", "release.v1", TEXT_A)
SPAN_B = span("span.v2", "release.v2", TEXT_B)


def build(cutoff: datetime, **overrides: Any) -> Any:
    base: dict[str, Any] = {
        "snapshot_id": "snapshot.0001",
        "instrument_ids": ["issuer.eq"],
        "research_cutoff": cutoff,
        "research_mode": HISTORICAL,
        "documents": [DOC_A, DOC_B],
        "spans": [SPAN_A, SPAN_B],
        "source_version": "test-sources-0",
        "frozen_at": FROZEN_AT,
    }
    base.update(overrides)
    return build_snapshot(**base)


# --- cutoff drives eligibility ------------------------------------------------------------


def test_a_cutoff_between_versions_sees_only_the_earlier_one() -> None:
    manifest = build(T2)

    assert manifest.document_ids == ("release.v1",)
    assert manifest.permitted_span_ids == ("span.v1",)


def test_a_later_cutoff_sees_the_correction() -> None:
    manifest = build(T3)

    assert manifest.document_ids == ("release.v2",)
    assert manifest.permitted_span_ids == ("span.v2",)


def test_changing_the_cutoff_changes_the_hash() -> None:
    assert build(T2).snapshot_hash != build(T3).snapshot_hash


def test_a_cutoff_before_anything_yields_an_empty_snapshot() -> None:
    manifest = build(datetime(2026, 1, 1, tzinfo=UTC))

    assert manifest.document_ids == ()


# --- immutability ---------------------------------------------------------------------------


def test_the_same_inputs_produce_the_same_hash() -> None:
    assert build(T2).snapshot_hash == build(T2).snapshot_hash


def test_assembly_order_does_not_change_the_hash() -> None:
    forward = build(T2, documents=[DOC_A, DOC_B], spans=[SPAN_A, SPAN_B])
    reverse = build(T2, documents=[DOC_B, DOC_A], spans=[SPAN_B, SPAN_A])

    assert forward.snapshot_hash == reverse.snapshot_hash


def test_freezing_the_same_evidence_later_is_the_same_snapshot() -> None:
    """frozen_at is excluded from the hash: the same evidence set is the same set."""
    later = build(T2, frozen_at=FROZEN_AT + timedelta(days=30))

    assert later.snapshot_hash == build(T2).snapshot_hash


def test_later_ingestion_cannot_alter_an_existing_snapshot() -> None:
    """The plan's acceptance case: a document arriving afterwards changes nothing."""
    original = build(T2)
    late_arrival = document("release.v3", T3 + timedelta(days=1))

    rebuilt = build(T2, documents=[DOC_A, DOC_B, late_arrival])

    assert rebuilt.snapshot_hash == original.snapshot_hash
    assert "release.v3" not in rebuilt.document_ids


def test_verification_detects_a_tampered_manifest() -> None:
    manifest = build(T2)

    assert verify_snapshot(manifest) is True
    assert verify_snapshot(manifest.model_copy(update={"snapshot_hash": "f" * 64})) is False


def test_verification_detects_an_added_document_id() -> None:
    manifest = build(T2)
    tampered = manifest.model_copy(update={"document_ids": ("release.v1", "release.v2")})

    assert verify_snapshot(tampered) is False


def test_the_hash_covers_the_source_version() -> None:
    common: dict[str, Any] = {
        "instrument_ids": ["issuer.eq"],
        "research_cutoff": T2,
        "document_ids": ["release.v1"],
        "span_ids": ["span.v1"],
        "claim_ids": [],
        "relation_ids": [],
        "ontology_version": 1,
    }

    assert compute_snapshot_hash(source_version="a", **common) != compute_snapshot_hash(
        source_version="b", **common
    )


# --- closure: nothing outside the manifest ---------------------------------------------------


def test_spans_for_excluded_documents_are_dropped() -> None:
    """A snapshot cannot reference a passage whose document did not qualify."""
    manifest = build(T2)

    assert "span.v2" not in manifest.permitted_span_ids


def test_a_view_refuses_a_document_outside_the_snapshot() -> None:
    manifest = build(T2)
    view = build_view(manifest, [DOC_A, DOC_B], [SPAN_A], {"release.v1": TEXT_A})

    assert view.document("release.v1") == DOC_A
    with pytest.raises(NotInSnapshotError, match="not in snapshot"):
        view.document("release.v2")


def test_a_view_refuses_a_span_outside_the_snapshot() -> None:
    view = build_view(build(T2), [DOC_A], [SPAN_A], {"release.v1": TEXT_A})

    with pytest.raises(NotInSnapshotError):
        view.span("span.v2")


def test_a_view_refuses_text_for_an_excluded_document() -> None:
    view = build_view(build(T2), [DOC_A], [SPAN_A], {"release.v1": TEXT_A})

    with pytest.raises(NotInSnapshotError):
        view.text("release.v2")


def test_a_view_cannot_be_built_with_a_permitted_span_missing() -> None:
    with pytest.raises(NotInSnapshotError, match="were not supplied"):
        build_view(build(T2), [DOC_A], [], {"release.v1": TEXT_A})


def test_the_cutoff_comes_from_the_manifest() -> None:
    """An agent cannot widen its window by supplying a later date."""
    view = build_view(build(T2), [DOC_A], [SPAN_A], {"release.v1": TEXT_A})

    assert view.research_cutoff == T2


# --- snapshot-scoped search --------------------------------------------------------------------


def test_search_is_confined_to_the_snapshot() -> None:
    view = build_view(build(T2), [DOC_A], [SPAN_A], {"release.v1": TEXT_A})

    assert [s.span_id for s in view.search("revenue", limit=6)] == ["span.v1"]
    assert view.search("corrected", limit=6) == ()


def test_search_respects_the_hit_limit() -> None:
    manifest = build(T3, documents=[DOC_B], spans=[SPAN_B])
    view = build_view(manifest, [DOC_B], [SPAN_B], {"release.v2": TEXT_B})

    assert len(view.search("revenue", limit=1)) == 1


def test_search_is_case_insensitive() -> None:
    view = build_view(build(T2), [DOC_A], [SPAN_A], {"release.v1": TEXT_A})

    assert len(view.search("REVENUE", limit=6)) == 1


# --- source completeness ------------------------------------------------------------------------


def completeness(**overrides: Any) -> SourceCompleteness:
    base: dict[str, Any] = {
        "source_id": "sec_edgar",
        "attempted": True,
        "succeeded": True,
        "document_count": 1,
    }
    base.update(overrides)
    return SourceCompleteness(**base)


def test_a_failed_source_stays_visible_in_the_snapshot() -> None:
    """Absent essential evidence must be visible, not merely absent."""
    manifest = build(
        T2,
        source_completeness=[
            completeness(),
            completeness(
                source_id="alpha_vantage",
                succeeded=False,
                document_count=0,
                failure_reason="alpha_vantage refused the request (Information: rate limit)",
            ),
        ],
    )
    view = build_view(manifest, [DOC_A], [SPAN_A], {"release.v1": TEXT_A})

    assert view.missing_sources == ("alpha_vantage",)


def test_a_failed_source_attempt_must_say_why() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="must say why"):
        completeness(succeeded=False, document_count=0)


def test_a_failed_source_cannot_claim_documents() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="contributed no documents"):
        completeness(succeeded=False, failure_reason="refused", document_count=3)


def test_a_source_cannot_succeed_without_being_attempted() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="without being attempted"):
        completeness(attempted=False, succeeded=True)


def test_an_empty_snapshot_reports_no_essential_evidence() -> None:
    manifest = build(datetime(2026, 1, 1, tzinfo=UTC))
    view = build_view(manifest, [], [], {})

    assert view.has_essential_evidence is False


def test_a_populated_snapshot_has_essential_evidence() -> None:
    view = build_view(build(T2), [DOC_A], [SPAN_A], {"release.v1": TEXT_A})

    assert view.has_essential_evidence is True


# --- lineage and derived records ------------------------------------------------------------------


def test_copies_of_one_release_share_a_source_family() -> None:
    """Two copies are one source; the snapshot must not present them as two confirmations."""
    copy = document("release.copy", T1, source_uri="https://mirror.invalid/release")

    assert copy.source_family_id == DOC_A.source_family_id


def test_only_the_latest_qualifying_version_of_a_family_is_included() -> None:
    copy = document("release.copy", T1, source_uri="https://mirror.invalid/release")
    manifest = build(T2, documents=[DOC_A, DOC_B, copy], spans=[SPAN_A, SPAN_B])

    assert len(manifest.document_ids) == 1


def test_a_claim_created_after_the_cutoff_is_excluded() -> None:
    """Rule 8: a claim written today is hindsight for a past cutoff."""
    claim = Claim(
        claim_id="claim.today",
        statement="Revenue was EUR 412.0 million.",
        subject_ids=("issuer.eq",),
        attribution="release",
        epistemic_status=EpistemicStatus.REPORTED,
        span_ids=("span.v1",),
        created_at=FROZEN_AT,
    )

    assert build(T2, claims=[claim]).permitted_claim_ids == ()


def test_a_claim_created_before_the_cutoff_is_included() -> None:
    claim = Claim(
        claim_id="claim.early",
        statement="Revenue was EUR 412.0 million.",
        subject_ids=("issuer.eq",),
        attribution="release",
        epistemic_status=EpistemicStatus.REPORTED,
        span_ids=("span.v1",),
        created_at=T1 + timedelta(hours=1),
    )

    assert build(T2, claims=[claim]).permitted_claim_ids == ("claim.early",)


def test_a_relation_touching_an_excluded_record_is_dropped() -> None:
    relation = Relation(
        relation_id="relation.excluded",
        predicate=RelationPredicate.HAS_SPAN,
        source_id="release.v2",
        target_id="span.v2",
        epistemic_status=EpistemicStatus.REPORTED,
        created_at=T1,
    )

    assert build(T2, relations=[relation]).permitted_relation_ids == ()


def test_a_relation_inside_the_snapshot_is_kept() -> None:
    relation = Relation(
        relation_id="relation.kept",
        predicate=RelationPredicate.HAS_SPAN,
        source_id="release.v1",
        target_id="span.v1",
        epistemic_status=EpistemicStatus.REPORTED,
        created_at=T1,
    )

    assert build(T2, relations=[relation]).permitted_relation_ids == ("relation.kept",)


# --- demo case manifests --------------------------------------------------------------------------


def test_the_three_real_cases_exist_and_are_marked_provisional() -> None:
    """Their case mapping is an intention, not a verified property of the filings."""
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "eval_cases"
    cases = [json.loads(p.read_text()) for p in sorted((root / "manifests").glob("*.json"))]

    assert [c["ticker"] for c in cases] == ["CALX", "LULU", "TSCO"]
    assert {c["status"] for c in cases} == {"PROVISIONAL"}
    assert {c["kind"] for c in cases} == {"real"}


def test_adversarial_cases_are_visibly_synthetic_and_separate() -> None:
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "eval_cases"
    variants = [json.loads(p.read_text()) for p in sorted((root / "development").glob("*.json"))]

    assert len(variants) == 5
    assert {v["kind"] for v in variants} == {"synthetic"}
    assert all(v["case_id"].startswith("synthetic-") for v in variants)


def test_the_source_failure_case_expects_source_failed_not_no_data() -> None:
    import json
    from pathlib import Path

    path = (
        Path(__file__).resolve().parents[2]
        / "eval_cases"
        / "development"
        / "synthetic-source-failure.json"
    )
    case = json.loads(path.read_text())

    assert case["expected_error_code"] == "SOURCE_FAILED"
    assert case["expected_disposition"] == "FAILED"
