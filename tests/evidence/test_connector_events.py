"""M2-T06 — every connector call is one ``connector.fetch`` span (amendments A11, A14).

Connectors put no content on spans: no body, no query string, no full URL, no key. The key in
these tests is deliberately NOT registered with the tracer's redaction, so it can only stay out
of the spans if the connector never records it.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from episalpha.connectors.filings import SecEdgarFilings
from episalpha.connectors.prices import AlphaVantagePrices, SourceError
from episalpha.connectors.xbrl import SecXbrlFacts
from episalpha.observability import configure_tracing, shutdown_tracing
from episalpha.settings import Settings
from episalpha.storage.objects import ObjectStore

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "connectors"
API_KEY = "AV-KEY-not-registered-1234"
AGENT = "EpisAlpha tests (owner@example.com)"


def responder(name: str) -> Any:
    def _transport(_: dict[str, str]) -> str:
        return (FIXTURES / name).read_text()

    return _transport


@pytest.fixture
def spans(tmp_path: Path) -> Iterator[InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    settings = Settings.model_validate(
        {"paths": {"project_root": tmp_path, "data_root": tmp_path / "data"}}
    )
    configure_tracing(settings, extra_exporter=exporter)
    yield exporter
    shutdown_tracing()


def only(exporter: InMemorySpanExporter) -> ReadableSpan:
    (fetch,) = exporter.get_finished_spans()
    assert fetch.name == "connector.fetch"
    return fetch


def attributes(fetch: ReadableSpan) -> dict[str, Any]:
    assert fetch.attributes is not None
    return dict(fetch.attributes)


def test_price_success_is_one_ok_span_with_size_and_hash(spans: InMemorySpanExporter) -> None:
    body = (FIXTURES / "alpha_vantage_daily.json").read_text()
    AlphaVantagePrices(responder("alpha_vantage_daily.json"), api_key=API_KEY).daily(
        "lulu.eq", "LULU"
    )

    fetch = only(spans)
    found = attributes(fetch)
    assert found["openinference.span.kind"] == "CHAIN"
    assert found["episalpha.source_id"] == "alpha_vantage"
    assert found["episalpha.operation"] == "daily"
    assert found["server.address"] == "www.alphavantage.co"
    assert found["episalpha.outcome"] == "ok"
    assert found["episalpha.bytes"] == len(body.encode())
    assert found["episalpha.payload_hash"] == hashlib.sha256(body.encode()).hexdigest()
    assert fetch.status.status_code is not StatusCode.ERROR


def test_throttle_is_source_failed_with_error_status(spans: InMemorySpanExporter) -> None:
    prices = AlphaVantagePrices(responder("alpha_vantage_throttled.json"), api_key=API_KEY)
    with pytest.raises(SourceError):
        prices.daily("lulu.eq", "LULU")

    fetch = only(spans)
    assert attributes(fetch)["episalpha.outcome"] == "SOURCE_FAILED"
    assert fetch.status.status_code is StatusCode.ERROR
    assert fetch.status.description == "SourceError: SOURCE_FAILED"


def test_empty_series_is_no_data(spans: InMemorySpanExporter) -> None:
    with pytest.raises(SourceError):
        AlphaVantagePrices(responder("alpha_vantage_empty.json")).daily("lulu.eq", "LULU")

    assert attributes(only(spans))["episalpha.outcome"] == "NO_DATA"


def test_transport_failure_is_source_failed(spans: InMemorySpanExporter) -> None:
    def broken(_: dict[str, str]) -> str:
        raise TimeoutError(f"timed out calling ...?apikey={API_KEY}")

    with pytest.raises(SourceError):
        AlphaVantagePrices(broken, api_key=API_KEY).daily("lulu.eq", "LULU")

    assert attributes(only(spans))["episalpha.outcome"] == "SOURCE_FAILED"


def test_no_key_body_or_query_string_in_any_span(spans: InMemorySpanExporter) -> None:
    prices = AlphaVantagePrices(responder("alpha_vantage_throttled.json"), api_key=API_KEY)
    with pytest.raises(SourceError):
        prices.daily("lulu.eq", "LULU")

    def broken(_: dict[str, str]) -> str:
        raise TimeoutError(f"timed out calling ...?apikey={API_KEY}")

    with pytest.raises(SourceError):
        AlphaVantagePrices(broken, api_key=API_KEY).daily("lulu.eq", "LULU")

    exported = "".join(item.to_json() for item in spans.get_finished_spans())
    throttle_text = (FIXTURES / "alpha_vantage_throttled.json").read_text()
    assert API_KEY not in exported
    assert "apikey" not in exported
    assert "?" not in exported.replace('"?"', "")
    for line in throttle_text.splitlines():
        stripped = line.strip().strip('",{}')
        if len(stripped) > 20:
            assert stripped not in exported


def test_sec_fetch_records_host_only(tmp_path: Path, spans: InMemorySpanExporter) -> None:
    edgar = SecEdgarFilings(
        ObjectStore(tmp_path / "o"), transport=responder("lulu_8k.html"), agent=AGENT
    )
    edgar.fetch("https://www.sec.gov/Archives/edgar/data/1397187/x/lulu.htm?secret=1")

    found = attributes(only(spans))
    assert found["episalpha.source_id"] == "sec_edgar"
    assert found["episalpha.operation"] == "fetch"
    assert found["server.address"] == "www.sec.gov"
    assert found["episalpha.outcome"] == "ok"
    assert "secret" not in "".join(item.to_json() for item in spans.get_finished_spans())


def test_xbrl_fetch_is_one_span(tmp_path: Path, spans: InMemorySpanExporter) -> None:
    xbrl = SecXbrlFacts(
        ObjectStore(tmp_path / "o"), transport=responder("companyfacts_lulu.json"), agent=AGENT
    )
    xbrl.fetch_companyfacts("0001397187")

    found = attributes(only(spans))
    assert found["episalpha.source_id"] == "sec_xbrl"
    assert found["episalpha.operation"] == "companyfacts"
    assert found["server.address"] == "data.sec.gov"
    assert found["episalpha.outcome"] == "ok"


def test_refused_host_is_a_failed_span(tmp_path: Path, spans: InMemorySpanExporter) -> None:
    edgar = SecEdgarFilings(ObjectStore(tmp_path / "o"), transport=responder("x"), agent=AGENT)
    with pytest.raises(SourceError):
        edgar.fetch("https://evil.example.com/steal")

    fetch = only(spans)
    assert attributes(fetch)["episalpha.outcome"] == "NOT_AUTHORIZED"
    assert fetch.status.status_code is StatusCode.ERROR


def test_one_span_per_call(spans: InMemorySpanExporter) -> None:
    prices = AlphaVantagePrices(responder("alpha_vantage_daily.json"))
    prices.daily("lulu.eq", "LULU")
    prices.daily("lulu.eq", "LULU")
    assert [item.name for item in spans.get_finished_spans()] == ["connector.fetch"] * 2
