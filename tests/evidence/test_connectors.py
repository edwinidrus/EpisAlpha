"""M2-T03 — connectors ingest recorded fixtures offline and keep failure kinds distinct.

Every response here is a recorded fixture. Nothing in this module touches the network, and a
`no_network` fixture makes that a test failure rather than a promise.
"""

from __future__ import annotations

import socket
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from episalpha.connectors.filings import (
    ALLOWED_HOSTS,
    FilingMetadata,
    SecEdgarFilings,
    check_allowed,
    user_agent,
)
from episalpha.connectors.prices import (
    AdjustmentBasis,
    AlphaVantagePrices,
    SourceError,
)
from episalpha.contracts.errors import ErrorCode
from episalpha.contracts.knowledge import AvailabilityBasis
from episalpha.contracts.research import ResearchMode
from episalpha.evidence.temporal import is_eligible
from episalpha.storage.objects import ObjectStore

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "connectors"
INGESTED_AT = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


def responder(name: str) -> Any:
    def _transport(_: dict[str, str]) -> str:
        return fixture(name)

    return _transport


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("a connector test attempted network access")

    monkeypatch.setattr(socket, "socket", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)


@pytest.fixture
def store(tmp_path: Path) -> ObjectStore:
    return ObjectStore(tmp_path / "objects")


# --- prices: recorded fixtures ingest offline -------------------------------------------


def prices(name: str) -> AlphaVantagePrices:
    return AlphaVantagePrices(responder(name), api_key="test-key", now=lambda: INGESTED_AT)


def test_a_recorded_response_ingests_without_network() -> None:
    series = prices("alpha_vantage_daily.json").daily("lulu.eq", "LULU")

    assert series.source_id == "alpha_vantage"
    assert len(series.points) == 3
    assert series.points[-1].trade_date == date(2026, 9, 18)


def test_a_series_carries_currency_date_basis_and_source() -> None:
    """The plan's acceptance wording, checked literally."""
    series = prices("alpha_vantage_daily.json").daily("lulu.eq", "LULU")

    assert series.currency == "USD"
    assert series.adjustment_basis is AdjustmentBasis.UNADJUSTED
    assert series.source_id == "alpha_vantage"
    assert all(point.trade_date is not None for point in series.points)
    assert series.fetched_at == INGESTED_AT


def test_points_are_ordered_oldest_first() -> None:
    series = prices("alpha_vantage_daily.json").daily("lulu.eq", "LULU")

    assert [p.trade_date for p in series.points] == sorted(p.trade_date for p in series.points)


def test_close_is_an_exact_decimal_not_a_float() -> None:
    from decimal import Decimal

    series = prices("alpha_vantage_daily.json").daily("lulu.eq", "LULU")

    assert series.close_on(date(2026, 9, 18)).close == Decimal("98.06")  # type: ignore[union-attr]


# --- prices: a refusal is never an absence ------------------------------------------------


@pytest.mark.parametrize("name", ["alpha_vantage_throttled.json", "alpha_vantage_premium.json"])
def test_a_refusal_is_source_failed_not_no_data(name: str) -> None:
    """Amendment A4: HTTP 200 plus an Information key is an outage, not an empty answer."""
    with pytest.raises(SourceError) as caught:
        prices(name).daily("lulu.eq", "LULU")

    assert caught.value.code is ErrorCode.SOURCE_FAILED
    assert "not an absence" in str(caught.value)


def test_an_empty_series_is_no_data() -> None:
    with pytest.raises(SourceError) as caught:
        prices("alpha_vantage_empty.json").daily("nosuch.eq", "NOSUCH")

    assert caught.value.code is ErrorCode.NO_DATA


def test_a_transport_failure_is_source_failed() -> None:
    def explode(_: dict[str, str]) -> str:
        raise TimeoutError("connection timed out")

    connector = AlphaVantagePrices(explode, api_key="test-key")

    with pytest.raises(SourceError) as caught:
        connector.daily("lulu.eq", "LULU")

    assert caught.value.code is ErrorCode.SOURCE_FAILED


def test_unparseable_content_is_source_failed() -> None:
    connector = AlphaVantagePrices(lambda _: "<html>error page</html>", api_key="k")

    with pytest.raises(SourceError) as caught:
        connector.daily("lulu.eq", "LULU")

    assert caught.value.code is ErrorCode.SOURCE_FAILED


# --- prices: current data cannot substitute for a historical request ----------------------


def test_as_of_truncates_rather_than_returning_todays_series() -> None:
    series = prices("alpha_vantage_daily.json").daily("lulu.eq", "LULU")

    narrowed = series.as_of(date(2026, 9, 17))

    assert narrowed is not None
    assert [p.trade_date for p in narrowed.points] == [date(2026, 9, 16), date(2026, 9, 17)]


def test_a_cutoff_before_any_observation_yields_nothing() -> None:
    series = prices("alpha_vantage_daily.json").daily("lulu.eq", "LULU")

    assert series.as_of(date(2026, 1, 1)) is None


# --- prices: the unadjusted rule is enforced, not documented -------------------------------


def test_a_return_cannot_be_computed_from_an_unadjusted_series() -> None:
    """Amendment A6: a split would manufacture a return that looks real and is not."""
    series = prices("alpha_vantage_daily.json").daily("lulu.eq", "LULU")

    with pytest.raises(SourceError, match="manufacture a false return"):
        series.simple_return(date(2026, 9, 16), date(2026, 9, 18))


def test_an_adjusted_series_may_compute_a_return() -> None:
    from decimal import Decimal

    series = prices("alpha_vantage_daily.json").daily("lulu.eq", "LULU")
    adjusted = series.model_copy(
        update={"adjustment_basis": AdjustmentBasis.SPLIT_AND_DIVIDEND_ADJUSTED}
    )

    result = adjusted.simple_return(date(2026, 9, 16), date(2026, 9, 18))

    assert result == (Decimal("98.06") - Decimal("95.40")) / Decimal("95.40")


def test_a_missing_close_is_no_data_not_zero() -> None:
    series = prices("alpha_vantage_daily.json").daily("lulu.eq", "LULU")
    adjusted = series.model_copy(
        update={"adjustment_basis": AdjustmentBasis.SPLIT_AND_DIVIDEND_ADJUSTED}
    )

    with pytest.raises(SourceError) as caught:
        adjusted.simple_return(date(2020, 1, 2), date(2026, 9, 18))

    assert caught.value.code is ErrorCode.NO_DATA


# --- filings: fair access and allowlisting ------------------------------------------------


def test_user_agent_requires_reachable_contact_details() -> None:
    assert "@" in user_agent("EpisAlpha/0.1", "owner@example.invalid")

    with pytest.raises(ValueError, match="contact details"):
        user_agent("EpisAlpha/0.1", "anonymous")


@pytest.mark.parametrize("host", sorted(ALLOWED_HOSTS))
def test_sec_hosts_are_allowed(host: str) -> None:
    check_allowed(f"https://{host}/Archives/edgar/data/1397187/x.htm")


def test_a_non_sec_host_is_refused() -> None:
    with pytest.raises(SourceError) as caught:
        check_allowed("https://evil.example.invalid/filing.htm")

    assert caught.value.code is ErrorCode.NOT_AUTHORIZED


def test_fetching_without_a_configured_transport_is_refused(store: ObjectStore) -> None:
    with pytest.raises(SourceError) as caught:
        SecEdgarFilings(store).fetch("https://www.sec.gov/Archives/edgar/data/1/x.htm")

    assert caught.value.code is ErrorCode.NOT_AUTHORIZED


# --- filings: submissions parsing ---------------------------------------------------------


def test_submissions_parse_into_filing_metadata(store: ObjectStore) -> None:
    filings = SecEdgarFilings(store).parse_submissions(fixture("sec_submissions.json"))

    assert [f.form_type for f in filings] == ["8-K", "10-Q"]
    assert filings[0].cik == "0001397187"
    assert filings[0].source_uri.startswith("https://www.sec.gov/Archives/edgar/data/1397187/")


def test_form_filtering_narrows_the_result(store: ObjectStore) -> None:
    filings = SecEdgarFilings(store).parse_submissions(
        fixture("sec_submissions.json"), forms=("8-K",)
    )

    assert [f.form_type for f in filings] == ["8-K"]


def test_no_filings_is_no_data(store: ObjectStore) -> None:
    with pytest.raises(SourceError) as caught:
        SecEdgarFilings(store).parse_submissions(fixture("sec_submissions_empty.json"))

    assert caught.value.code is ErrorCode.NO_DATA


def test_a_truncated_response_is_source_failed(store: ObjectStore) -> None:
    """We did not get to look, which is not the same as there being nothing to see."""
    with pytest.raises(SourceError) as caught:
        SecEdgarFilings(store).parse_submissions('{"cik": 1397187}')

    assert caught.value.code is ErrorCode.SOURCE_FAILED


def test_requesting_an_absent_form_is_no_data(store: ObjectStore) -> None:
    with pytest.raises(SourceError) as caught:
        SecEdgarFilings(store).parse_submissions(fixture("sec_submissions.json"), forms=("S-1",))

    assert caught.value.code is ErrorCode.NO_DATA


# --- filings: ingestion and the three clocks ------------------------------------------------


def metadata(**overrides: Any) -> FilingMetadata:
    base: dict[str, Any] = {
        "accession_number": "0001397187-26-000045",
        "cik": "0001397187",
        "form_type": "8-K",
        "filing_date": datetime(2026, 9, 4, tzinfo=UTC),
        "acceptance_datetime": datetime(2026, 9, 4, 16, 31, 5, tzinfo=UTC),
        "primary_document": "lulu-20260904.htm",
        "source_uri": "https://www.sec.gov/Archives/edgar/data/1397187/x/lulu-20260904.htm",
    }
    base.update(overrides)
    return FilingMetadata(**base)


def ingest(store: ObjectStore, **overrides: Any) -> tuple[Any, str]:
    connector = SecEdgarFilings(store, now=lambda: INGESTED_AT)
    payload = (FIXTURES / "lulu_8k.html").read_bytes()
    return connector.ingest(metadata(**overrides), payload, document_id="lulu-8k.v1")


def test_ingestion_preserves_the_original_bytes(store: ObjectStore) -> None:
    document, _ = ingest(store)

    assert store.get(document.payload_hash) == (FIXTURES / "lulu_8k.html").read_bytes()


def test_ingestion_strips_active_content_from_the_text(store: ObjectStore) -> None:
    _, text = ingest(store)

    assert "not prose" not in text
    assert "The Company now expects full year net revenue to decline 5% to 7%." in text


def test_acceptance_time_becomes_verified_availability(store: ObjectStore) -> None:
    """EDGAR acceptance is the moment of dissemination, so it is defensible availability."""
    document, _ = ingest(store)

    assert document.availability_basis is AvailabilityBasis.PROVIDER_VERIFIED
    assert document.public_available_at == datetime(2026, 9, 4, 16, 31, 5, tzinfo=UTC)
    assert document.published_at == datetime(2026, 9, 4, tzinfo=UTC)
    assert document.ingested_at == INGESTED_AT


def test_a_filing_date_alone_does_not_prove_availability(store: ObjectStore) -> None:
    """Without acceptance, our own capture is the conservative eligibility time."""
    document, _ = ingest(store, acceptance_datetime=None)

    assert document.availability_basis is AvailabilityBasis.FIRST_CAPTURE
    assert document.public_available_at == INGESTED_AT
    assert document.published_at == datetime(2026, 9, 4, tzinfo=UTC)


def test_an_unaccepted_filing_cannot_reach_back_to_its_filing_date(store: ObjectStore) -> None:
    """The temporal policy and the connector agree: no acceptance, no historical eligibility."""
    verified, _ = ingest(store)
    unverified, _ = ingest(store, acceptance_datetime=None)
    cutoff = datetime(2026, 9, 10, tzinfo=UTC)

    assert is_eligible(verified, cutoff, ResearchMode.HISTORICAL_RECONSTRUCTION) is True
    assert is_eligible(unverified, cutoff, ResearchMode.HISTORICAL_RECONSTRUCTION) is False


def test_copies_of_one_filing_share_a_source_family(store: ObjectStore) -> None:
    """Two copies of the same filing are not independent confirmation."""
    first, _ = ingest(store)
    second_metadata = metadata(source_uri="https://www.sec.gov/Archives/edgar/data/1397187/alt.htm")

    assert second_metadata.source_family_id == first.source_family_id


def test_a_different_filing_has_a_different_family(store: ObjectStore) -> None:
    first, _ = ingest(store)
    other = metadata(accession_number="0001397187-26-000031", form_type="10-Q")

    assert other.source_family_id != first.source_family_id
