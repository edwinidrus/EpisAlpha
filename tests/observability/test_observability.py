"""Whole-system tracing (M0-T06, amendments A11 and A14).

An ``InMemorySpanExporter`` stands in for Phoenix: it receives what the OTLP exporter would
(full content, redacted). The JSONL fallback is read back as text, so a secret or a content
value hiding anywhere in it fails the test.
"""

from __future__ import annotations

import json
import socket
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode
from pydantic import ValidationError

from episalpha.observability import (
    SpanKind,
    active_exporters,
    bind_run,
    configure_tracing,
    event,
    shutdown_tracing,
    span,
    trace_id_hex,
    trace_url,
)
from episalpha.settings import ObservabilityConfig, Settings

SECRET = "s3cr3t-value"


def make_settings(tmp_path: Path, **observability: object) -> Settings:
    return Settings.model_validate(
        {
            "paths": {"project_root": tmp_path, "data_root": tmp_path / "data"},
            "provider": {"api_key_env": "ENV:TEST_SECRET"},
            "sources": {
                "sources": [
                    {
                        "source_id": "sec_edgar",
                        "family": "fundamentals",
                        "provenance": "primary",
                        "api_key_env": "ENV:TEST_SOURCE_SECRET",
                    }
                ]
            },
            "observability": observability,
        }
    )


def spans_file(tmp_path: Path) -> Path:
    return tmp_path / "data" / "logs" / "spans.jsonl"


def jsonl_records(tmp_path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in spans_file(tmp_path).read_text().splitlines()]


@pytest.fixture(autouse=True)
def _reset() -> Iterator[None]:
    yield
    shutdown_tracing()


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("TEST_SECRET", SECRET)
    monkeypatch.setenv("TEST_SOURCE_SECRET", "source-key-123456")
    return make_settings(tmp_path)


@pytest.fixture
def memory(settings: Settings) -> InMemorySpanExporter:
    exporter = InMemorySpanExporter()
    configure_tracing(settings, extra_exporter=exporter)
    return exporter


def test_nested_spans_form_one_trace(memory: InMemorySpanExporter) -> None:
    with span("research.run", SpanKind.CHAIN) as outer, span("tool.search", SpanKind.RETRIEVER):
        pass

    inner_span, outer_span = memory.get_finished_spans()
    assert inner_span.parent is not None
    assert inner_span.parent.span_id == outer_span.context.span_id
    assert inner_span.context.trace_id == outer_span.context.trace_id
    assert trace_id_hex(outer) == f"{outer_span.context.trace_id:032x}"
    assert inner_span.attributes is not None
    assert inner_span.attributes["openinference.span.kind"] == "RETRIEVER"
    assert inner_span.attributes["outcome"] == "ok"


def test_bind_run_sets_session_on_every_span(memory: InMemorySpanExporter) -> None:
    with bind_run("run_0001"), span("research.run", SpanKind.CHAIN):
        with span("model.call", SpanKind.LLM):
            pass
    with span("cli.version", SpanKind.CHAIN):
        pass

    llm, run, cli = memory.get_finished_spans()
    for bound in (llm, run):
        assert bound.attributes is not None
        assert bound.attributes["session.id"] == "run_0001"
        assert bound.attributes["episalpha.run_id"] == "run_0001"
    assert cli.attributes is not None
    assert "session.id" not in cli.attributes


def test_exception_sets_error_status_and_reraises(memory: InMemorySpanExporter) -> None:
    with pytest.raises(ValueError, match="boom"), span("validation", SpanKind.EVALUATOR):
        raise ValueError("boom")

    (failed,) = memory.get_finished_spans()
    assert failed.status.status_code is StatusCode.ERROR
    assert failed.attributes is not None
    assert failed.attributes["outcome"] == "ValueError"


def test_secret_appears_in_no_exporter(memory: InMemorySpanExporter, tmp_path: Path) -> None:
    with pytest.raises(RuntimeError), bind_run("run_0002"):
        with span(
            "model.call",
            SpanKind.LLM,
            **{"input.value": f"key {SECRET}", "headers": ["ok", f"Bearer {SECRET}"]},
        ):
            event("model.retry", detail=f"retrying with {SECRET}", nested=["x", SECRET])
            raise RuntimeError(f"provider echoed {SECRET} and source-key-123456")
    configure_tracing(make_settings(tmp_path)).force_flush()

    exported = "".join(item.to_json() for item in memory.get_finished_spans())
    assert "***" in exported
    assert SECRET not in exported
    assert "source-key-123456" not in exported
    text = spans_file(tmp_path).read_text()
    assert SECRET not in text
    assert "source-key-123456" not in text


def test_jsonl_holds_metadata_only(memory: InMemorySpanExporter, tmp_path: Path) -> None:
    with span(
        "tool.search_evidence",
        SpanKind.RETRIEVER,
        **{"input.value": "demand weakness", "output.value": "span text", "hits": 3},
    ):
        event("validation.check", **{"input.value": "event content"})
    configure_tracing(make_settings(tmp_path)).force_flush()

    (record,) = jsonl_records(tmp_path)
    attributes = record["attributes"]
    assert isinstance(attributes, dict)
    assert "input.value" not in attributes
    assert "output.value" not in attributes
    assert attributes["input.value_bytes"] == len(b"demand weakness")
    assert len(attributes["input.value_hash"]) == 64
    assert attributes["hits"] == 3
    assert record["kind"] == "RETRIEVER"
    assert record["name"] == "tool.search_evidence"
    text = spans_file(tmp_path).read_text()
    assert "demand weakness" not in text
    assert "event content" not in text
    # The content exporter (Phoenix's stand-in) still receives full content.
    (full,) = memory.get_finished_spans()
    assert full.attributes is not None
    assert full.attributes["input.value"] == "demand weakness"


def test_without_endpoint_only_jsonl_is_active(settings: Settings) -> None:
    configure_tracing(settings)
    assert active_exporters() == ("jsonl",)
    assert trace_url("0" * 32) is None


def test_unreachable_phoenix_never_reaches_the_caller(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        closed_port = probe.getsockname()[1]
    endpoint = f"http://127.0.0.1:{closed_port}/v1/traces"
    provider = configure_tracing(
        make_settings(tmp_path, otlp_endpoint=endpoint, export_timeout_seconds=1)
    )
    assert active_exporters() == ("jsonl", "otlp")

    with span("research.run", SpanKind.CHAIN) as root:
        pass
    provider.force_flush(timeout_millis=5000)

    assert [record["name"] for record in jsonl_records(tmp_path)] == ["research.run"]
    trace_id = trace_id_hex(root)
    assert trace_url(trace_id) == f"http://127.0.0.1:{closed_port}/redirects/traces/{trace_id}"
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize(
    "endpoint",
    ["http://10.0.0.5:6006/v1/traces", "https://phoenix.example.com/v1/traces", "ftp://127.0.0.1"],
)
def test_non_loopback_endpoint_is_refused(endpoint: str) -> None:
    with pytest.raises(ValidationError, match="loopback"):
        ObservabilityConfig(otlp_endpoint=endpoint)


@pytest.mark.parametrize(
    "endpoint",
    ["http://127.0.0.1:6006/v1/traces", "http://localhost:6006/v1/traces", "http://[::1]:6006"],
)
def test_loopback_endpoint_is_accepted(endpoint: str) -> None:
    assert ObservabilityConfig(otlp_endpoint=endpoint).otlp_endpoint == endpoint


def test_configure_is_idempotent(settings: Settings) -> None:
    exporter = InMemorySpanExporter()
    first = configure_tracing(settings, extra_exporter=exporter)
    second = configure_tracing(settings, extra_exporter=exporter)
    assert first is second

    with span("cli.version", SpanKind.CHAIN):
        pass
    assert len(exporter.get_finished_spans()) == 1


def test_values_are_converted(memory: InMemorySpanExporter) -> None:
    class Opaque:
        def __repr__(self) -> str:
            return "x" * 500

    with span(
        "snapshot.freeze",
        SpanKind.CHAIN,
        amount=Decimal("1.10"),
        cutoff=datetime(2026, 9, 1, tzinfo=UTC),
        path=Path("/tmp/a"),
        mapping={"b": 1, "a": 2},
        opaque=Opaque(),
        missing=None,
    ):
        pass

    (frozen,) = memory.get_finished_spans()
    attributes = frozen.attributes
    assert attributes is not None
    assert attributes["amount"] == "1.10"
    assert attributes["cutoff"] == "2026-09-01T00:00:00+00:00"
    assert attributes["path"] == "/tmp/a"
    assert attributes["mapping"] == '{"a": 2, "b": 1}'
    assert attributes["opaque"] == "x" * 200
    assert "missing" not in attributes


def test_unconfigured_tracing_is_a_silent_no_op() -> None:
    with span("cli.version", SpanKind.CHAIN) as current:
        event("nothing")
    assert not current.is_recording()
    event("outside any span")


def test_default_suite_cannot_reach_the_network() -> None:
    with pytest.raises(AssertionError, match="default test suite attempted"):
        socket.create_connection(("192.0.2.1", 80), timeout=0.1)
