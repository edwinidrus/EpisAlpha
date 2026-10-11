"""M2-T05 — point-in-time XBRL facts (amendment A8).

The fixture is cut from LULU's real ``companyfacts`` payload (fetched 2026-10-10; SHA-256 of the
full payload is in the task journal), keeping SEC's own byte formatting for every fact object.
Acceptance times below are copied from LULU's real submissions payload.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from fixtures.synthetic_knowledge import SYNTHETIC_ENTITY

from episalpha.connectors import xbrl
from episalpha.connectors.prices import SourceError
from episalpha.connectors.xbrl import SecXbrlFacts, XbrlFact
from episalpha.contracts.errors import ErrorCode
from episalpha.contracts.knowledge import (
    AvailabilityBasis,
    Claim,
    Derivation,
    EpistemicStatus,
)
from episalpha.contracts.research import ResearchMode
from episalpha.evidence.temporal import select_current_versions
from episalpha.research.validation import RecordSet, failed_checks, validate
from episalpha.storage.objects import ObjectStore

FIXTURE = Path(__file__).parents[1] / "fixtures" / "connectors" / "companyfacts_lulu.json"
CIK = "0001397187"
ACCRUED = "AccruedLiabilitiesCurrent"
REVENUE = "RevenueFromContractWithCustomerExcludingAssessedTax"

ORIGINAL = "0001397187-21-000018"  # 10-Q, value 211911000
RESTATED = "0001397187-22-000014"  # 10-K, value 226867000, same instant 2021-01-31
ACCEPTED = {
    ORIGINAL: datetime(2021, 6, 4, 0, 18, 14, tzinfo=UTC),
    "0001397187-21-000027": datetime(2021, 9, 9, 0, 17, 32, tzinfo=UTC),
    "0001397187-21-000039": datetime(2021, 12, 10, 2, 16, 32, tzinfo=UTC),
    RESTATED: datetime(2022, 3, 30, 0, 16, 2, tzinfo=UTC),
    "0001397187-25-000039": datetime(2025, 9, 5, 0, 12, 44, tzinfo=UTC),
    "0001397187-26-000127": datetime(2026, 9, 4, 0, 10, 9, tzinfo=UTC),
}
INSTANT = (None, date(2021, 1, 31))
NOW = datetime(2026, 10, 10, 22, 0, tzinfo=UTC)


@pytest.fixture
def connector(tmp_path: Path) -> SecXbrlFacts:
    return SecXbrlFacts(ObjectStore(tmp_path / "objects"), now=lambda: NOW)


@pytest.fixture
def body() -> bytes:
    return FIXTURE.read_bytes()


@pytest.fixture
def facts(connector: SecXbrlFacts, body: bytes) -> list[XbrlFact]:
    return connector.parse(body)


def test_parse_reads_every_fact_with_verified_field_names(facts: list[XbrlFact]) -> None:
    assert len(facts) == 6
    restated = next(f for f in facts if f.accession == RESTATED)
    assert restated.taxonomy == "us-gaap"
    assert restated.concept == ACCRUED
    assert restated.unit == "USD"
    assert restated.start is None
    assert restated.end == date(2021, 1, 31)
    assert restated.value == Decimal("226867000")
    assert (restated.form, restated.fp, restated.fy) == ("10-K", "FY", 2021)
    assert restated.filed == date(2022, 3, 29)
    assert restated.frame == "CY2020Q4I"
    assert restated.locator == f"us-gaap:{ACCRUED}/USD[3]"


def test_decimal_values_survive_exactly(connector: SecXbrlFacts) -> None:
    body = json.dumps(
        {
            "cik": 1,
            "facts": {
                "us-gaap": {
                    "Revenues": {
                        "units": {"USD": []},
                    }
                }
            },
        }
    ).replace(
        '"USD": []',
        '"USD": [{"start":"2025-01-01","end":"2025-03-31","val":1234567.89,'
        '"accn":"0000000001-25-000001","fy":2025,"fp":"Q1","form":"10-Q","filed":"2025-05-01"}]',
    )
    (fact,) = connector.parse(body.encode())
    assert fact.value == Decimal("1234567.89")
    assert str(fact.value) == "1234567.89"


def test_as_of_selection_never_lets_a_later_restatement_win(facts: list[XbrlFact]) -> None:
    between = datetime(2022, 1, 1, tzinfo=UTC)
    after = datetime(2022, 4, 1, tzinfo=UTC)
    before_any = datetime(2021, 6, 1, tzinfo=UTC)

    at_t2 = SecXbrlFacts.select_as_of(facts, ACCRUED, "USD", INSTANT, ACCEPTED, between)
    at_t4 = SecXbrlFacts.select_as_of(facts, ACCRUED, "USD", INSTANT, ACCEPTED, after)

    assert at_t2 is not None and at_t2.value == Decimal("211911000")
    assert at_t2.accession == "0001397187-21-000039"  # latest accepted before the cutoff
    assert at_t4 is not None and at_t4.value == Decimal("226867000")
    assert at_t4.accession == RESTATED
    assert SecXbrlFacts.select_as_of(facts, ACCRUED, "USD", INSTANT, ACCEPTED, before_any) is None


def test_acceptance_exactly_at_the_cutoff_is_eligible(facts: list[XbrlFact]) -> None:
    chosen = SecXbrlFacts.select_as_of(facts, ACCRUED, "USD", INSTANT, ACCEPTED, ACCEPTED[ORIGINAL])
    assert chosen is not None and chosen.accession == ORIGINAL


def test_unknown_availability_is_ineligible_whatever_the_filed_date(
    facts: list[XbrlFact],
) -> None:
    partial = {ORIGINAL: None, RESTATED: ACCEPTED[RESTATED]}
    cutoff = datetime(2022, 1, 1, tzinfo=UTC)  # every fact's `filed` date is before this
    assert SecXbrlFacts.select_as_of(facts, ACCRUED, "USD", INSTANT, partial, cutoff) is None


def test_unknown_concept_is_no_data(facts: list[XbrlFact]) -> None:
    with pytest.raises(SourceError) as raised:
        SecXbrlFacts.select_as_of(facts, "Revenues", "USD", INSTANT, ACCEPTED, NOW)
    assert raised.value.code is ErrorCode.NO_DATA


@pytest.mark.parametrize(
    "payload",
    [b"<html>rate limited</html>", b'{"cik": 1}', b'{"facts": []}', b"\xff\xfe"],
)
def test_malformed_payload_is_source_failed(connector: SecXbrlFacts, payload: bytes) -> None:
    with pytest.raises(SourceError) as raised:
        connector.parse(payload)
    assert raised.value.code is ErrorCode.SOURCE_FAILED


def test_empty_facts_is_no_data(connector: SecXbrlFacts) -> None:
    with pytest.raises(SourceError) as raised:
        connector.parse(b'{"cik": 1, "facts": {}}')
    assert raised.value.code is ErrorCode.NO_DATA


def test_fetch_uses_the_allowlisted_companyfacts_url(tmp_path: Path, body: bytes) -> None:
    seen: list[dict[str, str]] = []

    def transport(request: dict[str, str]) -> str:
        seen.append(request)
        return body.decode()

    connector = SecXbrlFacts(
        ObjectStore(tmp_path / "o"), transport=transport, agent="EpisAlpha (owner@example.com)"
    )
    assert connector.fetch_companyfacts(CIK) == body
    assert seen == [
        {
            "url": "https://data.sec.gov/api/xbrl/companyfacts/CIK0001397187.json",
            "User-Agent": "EpisAlpha (owner@example.com)",
        }
    ]


def test_fetch_without_transport_is_not_authorized(connector: SecXbrlFacts) -> None:
    with pytest.raises(SourceError) as raised:
        connector.fetch_companyfacts(CIK)
    assert raised.value.code is ErrorCode.NOT_AUTHORIZED


def test_fetch_failure_is_source_failed(tmp_path: Path) -> None:
    def broken(request: dict[str, str]) -> str:
        raise TimeoutError("read timed out")

    connector = SecXbrlFacts(ObjectStore(tmp_path / "o"), transport=broken, agent="A (a@b.c)")
    with pytest.raises(SourceError) as raised:
        connector.fetch_companyfacts(CIK)
    assert raised.value.code is ErrorCode.SOURCE_FAILED


def test_malformed_cik_is_rejected_before_any_url_is_built(connector: SecXbrlFacts) -> None:
    with pytest.raises(SourceError) as raised:
        connector.fetch_companyfacts("../../frames/us-gaap")
    assert raised.value.code is ErrorCode.INVALID_REQUEST


def test_no_code_path_builds_a_frames_url() -> None:
    source = Path(xbrl.__file__).read_text()
    assert "xbrl/frames" not in source
    assert "/frames/" not in source


def test_evidence_quotes_the_exact_fact_object(
    connector: SecXbrlFacts, body: bytes, facts: list[XbrlFact]
) -> None:
    chosen = SecXbrlFacts.select_as_of(facts, ACCRUED, "USD", INSTANT, ACCEPTED, NOW)
    assert chosen is not None

    accepted = ACCEPTED[RESTATED]
    document, span, text = connector.ingest_fact(chosen, body, cik=CIK, accepted_at=accepted)

    assert span.exact_quote == text[span.start_offset : span.end_offset]
    assert span.exact_quote == (
        '{"end":"2021-01-31","val":226867000,"accn":"0001397187-22-000014","fy":2021,'
        '"fp":"FY","form":"10-K","filed":"2022-03-29","frame":"CY2020Q4I"}'
    )
    assert span.section_locator == f"us-gaap:{ACCRUED}/USD[3]"
    assert connector.object_store.get(document.payload_hash) == body
    assert document.availability_basis is AvailabilityBasis.PROVIDER_VERIFIED
    assert document.public_available_at == ACCEPTED[RESTATED]
    assert document.published_at == datetime(2022, 3, 29, tzinfo=UTC)
    assert document.ingested_at == NOW


def test_restated_fact_documents_are_versions_of_one_family(
    connector: SecXbrlFacts, body: bytes, facts: list[XbrlFact]
) -> None:
    original = next(f for f in facts if f.accession == ORIGINAL)
    restated = next(f for f in facts if f.accession == RESTATED)
    doc_a, _, _ = connector.ingest_fact(original, body, cik=CIK, accepted_at=ACCEPTED[ORIGINAL])
    doc_b, _, _ = connector.ingest_fact(restated, body, cik=CIK, accepted_at=ACCEPTED[RESTATED])

    assert doc_a.source_family_id == doc_b.source_family_id
    assert doc_a.document_id != doc_b.document_id
    mode = ResearchMode.HISTORICAL_RECONSTRUCTION
    (at_t2,) = select_current_versions([doc_a, doc_b], datetime(2022, 1, 1, tzinfo=UTC), mode)
    (at_t4,) = select_current_versions([doc_a, doc_b], datetime(2022, 4, 1, tzinfo=UTC), mode)
    assert at_t2 == doc_a
    assert at_t4 == doc_b


def test_ingest_without_acceptance_falls_back_to_first_capture(
    connector: SecXbrlFacts, body: bytes, facts: list[XbrlFact]
) -> None:
    document, _, _ = connector.ingest_fact(facts[0], body, cik=CIK, accepted_at=None)
    assert document.availability_basis is AvailabilityBasis.FIRST_CAPTURE
    assert document.public_available_at == NOW


def test_numeric_fact_and_a_recomputed_derivation(
    connector: SecXbrlFacts, body: bytes, facts: list[XbrlFact]
) -> None:
    """End to end with M1-T05: two XBRL facts feed a derivation the validator recomputes."""
    original = next(f for f in facts if f.accession == ORIGINAL)
    restated = next(f for f in facts if f.accession == RESTATED)
    claims = []
    documents, spans, texts = [], [], {}
    for name, fact, accepted in (
        ("claim.accrued-10q", original, ACCEPTED[ORIGINAL]),
        ("claim.accrued-10k", restated, ACCEPTED[RESTATED]),
    ):
        document, span, text = connector.ingest_fact(fact, body, cik=CIK, accepted_at=accepted)
        documents.append(document)
        spans.append(span)
        texts[document.document_id] = text
        numeric = SecXbrlFacts.to_numeric_fact(fact)
        assert numeric.metric == f"us-gaap:{ACCRUED}"
        assert numeric.period_start == numeric.period_end == datetime(2021, 1, 31, tzinfo=UTC)
        assert numeric.accounting_basis == "us-gaap"
        assert fact.accession in numeric.source_context
        claims.append(
            Claim(
                claim_id=name,
                statement=f"{ACCRUED} was {fact.value} USD at 2021-01-31.",
                subject_ids=(SYNTHETIC_ENTITY.entity_id,),
                attribution=f"SEC XBRL companyfacts, accession {fact.accession}",
                epistemic_status=EpistemicStatus.REPORTED,
                span_ids=(span.span_id,),
                numeric_fact=numeric,
                created_at=NOW,
            )
        )
    revision = SecXbrlFacts.to_numeric_fact(restated).model_copy(
        update={"value": Decimal("14956000"), "source_context": "difference of two filings"}
    )
    claims.append(
        Claim(
            claim_id="claim.accrued-restatement",
            statement="The 10-K restated accrued liabilities up by USD 14,956,000.",
            subject_ids=(SYNTHETIC_ENTITY.entity_id,),
            attribution="EpisAlpha derivation",
            epistemic_status=EpistemicStatus.DERIVED,
            derivation=Derivation(
                method="difference",
                method_version="1",
                input_claim_ids=("claim.accrued-10q", "claim.accrued-10k"),
            ),
            numeric_fact=revision,
            created_at=NOW,
        )
    )
    report = validate(
        RecordSet(
            entities=[SYNTHETIC_ENTITY],
            documents=documents,
            spans=spans,
            claims=claims,
            document_texts=texts,
        ),
        run_id="run.0001",
    )
    assert failed_checks(report) == ()
    assert report.structurally_valid
