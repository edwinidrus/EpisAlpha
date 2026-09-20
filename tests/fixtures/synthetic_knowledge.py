"""SYNTHETIC test fixtures. Not real companies, filings, figures, or research.

Everything here is invented for testing the contracts. The issuer "Synthetic Test Issuer NV"
does not exist, and no number below describes any real business. Nothing in this module may be
presented as evidence, or copied into a demo corpus.
"""

from __future__ import annotations

from datetime import UTC, datetime

from episalpha.contracts.knowledge import (
    AvailabilityBasis,
    Claim,
    Entity,
    EpistemicStatus,
    EvidenceDocument,
    EvidenceSpan,
    Hypothesis,
    Instrument,
    NumericFact,
)

PUBLISHED_AT = datetime(2026, 2, 10, 21, 5, tzinfo=UTC)
INGESTED_AT = datetime(2026, 2, 11, 6, 0, tzinfo=UTC)
CREATED_AT = datetime(2026, 9, 20, 9, 30, tzinfo=UTC)

DOCUMENT_TEXT = (
    "Fourth quarter revenue reached EUR 412.0 million. "
    "Management expects demand to soften during the first half."
)

SYNTHETIC_ENTITY = Entity(
    entity_id="synthetic-issuer",
    kind="corporation",
    canonical_name="Synthetic Test Issuer NV",
    aliases=("Synthetic Test Issuer",),
    external_identifiers={"test_registry": "SYN-0001"},
)

SYNTHETIC_INSTRUMENT = Instrument(
    instrument_id="synthetic-issuer.eq",
    issuer_entity_id="synthetic-issuer",
    exchange="TESTEX",
    currency="EUR",
)

SYNTHETIC_DOCUMENT = EvidenceDocument(
    document_id="synthetic-doc.v1",
    source_uri="https://example.invalid/synthetic/q4-release",
    source_type="company_release",
    source_family_id="synthetic-release-family",
    payload_hash="a" * 64,
    parsed_text_hash="b" * 64,
    parser_version="test-parser-0",
    published_at=PUBLISHED_AT,
    public_available_at=PUBLISHED_AT,
    availability_basis=AvailabilityBasis.PROVIDER_VERIFIED,
    ingested_at=INGESTED_AT,
)

# Offsets are exact character positions in DOCUMENT_TEXT; the contract checks they agree.
REVENUE_SPAN = EvidenceSpan(
    span_id="synthetic-span.revenue",
    document_id="synthetic-doc.v1",
    start_offset=0,
    end_offset=52,
    exact_quote=DOCUMENT_TEXT[0:52],
    section_locator="paragraph-1",
)

DEMAND_SPAN = EvidenceSpan(
    span_id="synthetic-span.demand",
    document_id="synthetic-doc.v1",
    start_offset=53,
    end_offset=DOCUMENT_TEXT.index("half.") + len("half."),
    exact_quote=DOCUMENT_TEXT[53:],
    section_locator="paragraph-2",
)

REPORTED_CLAIM = Claim(
    claim_id="synthetic-claim.revenue",
    statement="The issuer reported fourth quarter revenue of EUR 412.0 million.",
    subject_ids=("synthetic-issuer.eq",),
    attribution="Synthetic Test Issuer NV quarterly release",
    epistemic_status=EpistemicStatus.REPORTED,
    span_ids=("synthetic-span.revenue",),
    numeric_fact=NumericFact(
        metric="revenue",
        value="412000000.00",
        unit="EUR",
        period_start=datetime(2025, 10, 1, tzinfo=UTC),
        period_end=datetime(2025, 12, 31, tzinfo=UTC),
        accounting_basis="IFRS consolidated, unaudited",
        source_context="Q4 synthetic release, headline figure",
    ),
    created_at=CREATED_AT,
)

CONTRADICTING_CLAIM = Claim(
    claim_id="synthetic-claim.demand",
    statement="The issuer expects demand to soften in the first half.",
    subject_ids=("synthetic-issuer.eq",),
    attribution="Synthetic Test Issuer NV quarterly release",
    epistemic_status=EpistemicStatus.REPORTED,
    span_ids=("synthetic-span.demand",),
    created_at=CREATED_AT,
)

SYNTHETIC_HYPOTHESIS = Hypothesis(
    hypothesis_id="synthetic-hypothesis.demand",
    mechanism=(
        "Softening guidance precedes order-book decline, which shows up in the following "
        "quarter's reported revenue."
    ),
    assumptions=(
        "Guidance language reflects management's order-book visibility.",
        "No offsetting price increase absorbs the volume decline.",
    ),
    supporting_claim_ids=("synthetic-claim.demand",),
    opposing_claim_ids=("synthetic-claim.revenue",),
    falsification_condition=(
        "Next reported quarterly revenue is at or above EUR 412.0 million on the same basis."
    ),
    horizon_trading_days=20,
    created_at=CREATED_AT,
)
