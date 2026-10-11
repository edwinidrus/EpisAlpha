"""Whole-system tracing: the runtime half of the Diagnose layer (amendments A11, A14).

Every I/O or trust boundary, AI or not, opens one OpenTelemetry span through :func:`span`. A
research run is one trace (root span ``research.run``, ``session.id`` = run ID, via
:func:`bind_run`).

Where spans go:

- always ``<data_root>/logs/spans.jsonl``, with content attributes (prompts, completions, tool
  parameters, retrieved text) replaced by a SHA-256 hash and a byte size;
- when ``observability.otlp_endpoint`` is set, a local Arize Phoenix over OTLP/HTTP, with full
  content unless ``capture_content`` is false.

Every resolved credential value is replaced by ``***`` before any exporter sees a span.

Spans are diagnostic, never canonical: no application logic reads them back, and no exporter
failure ever reaches the caller (global constitution articles 27-29). Unconfigured, every
function here is a silent no-op, so library code can always call :func:`span`.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from threading import Lock
from typing import Any

from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import Event, ReadableSpan, SpanProcessor, TracerProvider
from opentelemetry.sdk.trace import Span as SdkSpan
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SimpleSpanProcessor,
    SpanExporter,
    SpanExportResult,
)
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.trace import Span, Status, StatusCode

from episalpha.settings import ObservabilityConfig, Settings

# OpenTelemetry reports export failures through `logging`. Without a handler, Python's
# last-resort handler would print them to stderr and pollute the CLI; the NullHandler stops
# that while still letting an application that configures logging see them.
logging.getLogger("opentelemetry").addHandler(logging.NullHandler())

KIND_ATTRIBUTE = "openinference.span.kind"
REDACTED = "***"
CONTENT_KEYS = frozenset({"input.value", "output.value", "tool.parameters"})
CONTENT_PREFIXES = ("llm.input_messages", "llm.output_messages", "retrieval.documents")
_CONTENT_REPR_LIMIT = 2000
_REPR_LIMIT = 200
_TRACER_NAME = "episalpha"


class SpanKind(StrEnum):
    """OpenInference span kinds used by EpisAlpha (global constitution article 27)."""

    CHAIN = "CHAIN"
    LLM = "LLM"
    TOOL = "TOOL"
    RETRIEVER = "RETRIEVER"
    AGENT = "AGENT"
    EVALUATOR = "EVALUATOR"


def is_content(key: str) -> bool:
    """Content attributes go to Phoenix only, never to the JSONL fallback."""
    return key in CONTENT_KEYS or key.startswith(CONTENT_PREFIXES)


# --- attribute values ----------------------------------------------------------------------

AttributeValue = str | bool | int | float | tuple[str, ...] | tuple[int, ...] | tuple[float, ...]


def _convert(key: str, value: object) -> AttributeValue | None:
    if value is None:
        return None
    if isinstance(value, str | bool | int | float):
        return value
    if isinstance(value, Decimal | Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return json.dumps(value, sort_keys=True, default=str)
    if isinstance(value, list | tuple):
        items = list(value)
        if all(isinstance(item, str) for item in items):
            return tuple(items)
        if all(isinstance(item, int) and not isinstance(item, bool) for item in items):
            return tuple(items)
        return json.dumps(items, default=str)
    return repr(value)[: _CONTENT_REPR_LIMIT if is_content(key) else _REPR_LIMIT]


def _attributes(values: Mapping[str, object]) -> dict[str, AttributeValue]:
    converted = {key: _convert(key, value) for key, value in values.items()}
    return {key: value for key, value in converted.items() if value is not None}


def annotate(target: Span, /, **attrs: object) -> None:
    """Add converted attributes to a span returned by :func:`span`."""
    target.set_attributes(_attributes(attrs))


# --- span rewriting ------------------------------------------------------------------------


def _scrub(value: Any, secrets: tuple[str, ...]) -> Any:
    if isinstance(value, str):
        for secret in secrets:
            value = value.replace(secret, REDACTED)
        return value
    if isinstance(value, list | tuple):
        return tuple(_scrub(item, secrets) for item in value)
    if isinstance(value, Mapping):
        return {key: _scrub(item, secrets) for key, item in value.items()}
    return value


def _metadata_only(attributes: Mapping[str, Any]) -> dict[str, Any]:
    kept: dict[str, Any] = {}
    for key, value in attributes.items():
        if not is_content(key):
            kept[key] = value
            continue
        text = value if isinstance(value, str) else json.dumps(list(value), default=str)
        data = text.encode()
        kept[f"{key}_hash"] = hashlib.sha256(data).hexdigest()
        kept[f"{key}_bytes"] = len(data)
    return kept


AttributeRewrite = Callable[[Mapping[str, Any]], dict[str, Any]]


def _rebuild(
    span: ReadableSpan, attributes: AttributeRewrite, description: str | None = None
) -> ReadableSpan:
    """A copy of ``span`` with attributes (and event attributes) rewritten by ``attributes``."""
    status = span.status
    if status.status_code is StatusCode.ERROR:
        status = Status(StatusCode.ERROR, description)
    return ReadableSpan(
        name=span.name,
        context=span.context,
        parent=span.parent,
        resource=span.resource,
        attributes=attributes(span.attributes or {}),
        events=[
            Event(item.name, attributes(item.attributes or {}), item.timestamp)
            for item in span.events
        ],
        links=span.links,
        kind=span.kind,
        status=status,
        start_time=span.start_time,
        end_time=span.end_time,
        instrumentation_scope=span.instrumentation_scope,
    )


class RedactionSpanProcessor(SpanProcessor):
    """Strips every secret from a finished span, then hands the copy to the real processors.

    It sits in front of every exporter, so no exporter ever sees a credential value. A failing
    downstream processor is swallowed: tracing never fails the caller.
    """

    def __init__(self, secrets: Sequence[str], processors: Sequence[SpanProcessor]) -> None:
        # Longest first, so a secret that contains another is replaced whole.
        self._secrets = tuple(sorted({item for item in secrets if item}, key=len, reverse=True))
        self._processors = tuple(processors)

    def redact(self, span: ReadableSpan) -> ReadableSpan:
        if not self._secrets:
            return span
        description = span.status.description
        return _rebuild(
            span,
            lambda attributes: {key: _scrub(v, self._secrets) for key, v in attributes.items()},
            _scrub(description, self._secrets) if description else None,
        )

    def on_start(self, span: SdkSpan, parent_context: Context | None = None) -> None:
        for processor in self._processors:
            processor.on_start(span, parent_context)

    def on_end(self, span: ReadableSpan) -> None:
        clean = self.redact(span)
        for processor in self._processors:
            try:
                processor.on_end(clean)
            except Exception:  # diagnostics must never fail the caller
                continue

    def shutdown(self) -> None:
        for processor in self._processors:
            try:
                processor.shutdown()
            except Exception:
                continue

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        results = []
        for processor in self._processors:
            try:
                results.append(processor.force_flush(timeout_millis))
            except Exception:
                results.append(False)
        return all(results)


# --- exporters -----------------------------------------------------------------------------


class MetadataOnlyExporter(SpanExporter):
    """Replaces content attributes with ``<key>_hash`` and ``<key>_bytes``, then delegates."""

    def __init__(self, inner: SpanExporter) -> None:
        self._inner = inner

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        rebuilt = [_rebuild(item, _metadata_only, item.status.description) for item in spans]
        return self._inner.export(rebuilt)

    def shutdown(self) -> None:
        self._inner.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._inner.force_flush(timeout_millis)


def _iso(nanoseconds: int | None) -> str | None:
    if nanoseconds is None:
        return None
    return datetime.fromtimestamp(nanoseconds / 1e9, UTC).isoformat(timespec="microseconds")


def _record(span: ReadableSpan) -> dict[str, Any]:
    context = span.get_span_context()
    attributes = dict(span.attributes or {})
    duration = None
    if span.start_time is not None and span.end_time is not None:
        duration = round((span.end_time - span.start_time) / 1e6, 3)
    return {
        "name": span.name,
        "trace_id": f"{context.trace_id:032x}" if context else None,
        "span_id": f"{context.span_id:016x}" if context else None,
        "parent_span_id": f"{span.parent.span_id:016x}" if span.parent else None,
        "kind": attributes.get(KIND_ATTRIBUTE),
        "start": _iso(span.start_time),
        "end": _iso(span.end_time),
        "duration_ms": duration,
        "status": span.status.status_code.name,
        "status_message": span.status.description,
        "attributes": attributes,
        "events": [
            {
                "name": item.name,
                "time": _iso(item.timestamp),
                "attributes": dict(item.attributes or {}),
            }
            for item in span.events
        ],
        "service": span.resource.attributes.get("service.name"),
    }


class JsonlSpanExporter(SpanExporter):
    """Appends one JSON line per span. Wrapped in :class:`MetadataOnlyExporter` by
    :func:`configure_tracing`, so it never holds content."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = Lock()

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        try:
            lines = "".join(json.dumps(_record(item), default=str) + "\n" for item in spans)
            with self._lock:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                with self._path.open("a", encoding="utf-8") as handle:
                    handle.write(lines)
        except (OSError, TypeError, ValueError):
            return SpanExportResult.FAILURE
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        return None


# --- configuration -------------------------------------------------------------------------

# ponytail: module-level provider, not the OpenTelemetry global one. The global provider can be
# set only once per process, which would make tests and re-configuration impossible; EpisAlpha
# has no third-party instrumentation that needs the global.
_provider: TracerProvider | None = None
_config: ObservabilityConfig | None = None
_exporters: tuple[str, ...] = ()
_run_id: ContextVar[str | None] = ContextVar("episalpha_run_id", default=None)


def _resolved_secrets(settings: Settings) -> list[str]:
    candidates = [settings.provider.credential()]
    candidates += [source.credential() for source in settings.sources.sources]
    return [item for item in candidates if item]


def configure_tracing(
    settings: Settings, *, extra_exporter: SpanExporter | None = None
) -> TracerProvider:
    """Install the tracer once per process; later calls return the same provider unchanged.

    ``extra_exporter`` is a test hook: it receives exactly what Phoenix would receive (full
    content, already redacted), synchronously.
    """
    global _provider, _config, _exporters
    if _provider is not None:
        return _provider
    config = settings.observability
    jsonl = JsonlSpanExporter(settings.paths.data_root / "logs" / "spans.jsonl")
    processors: list[SpanProcessor] = [BatchSpanProcessor(MetadataOnlyExporter(jsonl))]
    names = ["jsonl"]
    if config.otlp_endpoint is not None:
        otlp: SpanExporter = OTLPSpanExporter(
            endpoint=config.otlp_endpoint, timeout=config.export_timeout_seconds
        )
        if not config.capture_content:
            otlp = MetadataOnlyExporter(otlp)
        processors.append(BatchSpanProcessor(otlp))
        names.append("otlp")
    if extra_exporter is not None:
        processors.append(SimpleSpanProcessor(extra_exporter))
    provider = TracerProvider(
        resource=Resource.create(
            {"service.name": config.service_name, "openinference.project.name": config.project_name}
        ),
        sampler=ParentBased(TraceIdRatioBased(config.sample_ratio)),
    )
    provider.add_span_processor(RedactionSpanProcessor(_resolved_secrets(settings), processors))
    _provider, _config, _exporters = provider, config, tuple(names)
    return provider


def shutdown_tracing() -> None:
    """Flush and close every exporter. Safe to call when tracing was never configured."""
    global _provider, _config, _exporters
    if _provider is not None:
        _provider.shutdown()
    _provider, _config, _exporters = None, None, ()


def active_exporters() -> tuple[str, ...]:
    """Names of the configured exporters, for status output: ``("jsonl",)`` or with ``"otlp"``."""
    return _exporters


# --- the API every boundary uses -----------------------------------------------------------


@contextmanager
def bind_run(run_id: str) -> Iterator[None]:
    """Every span opened inside carries ``session.id`` and ``episalpha.run_id``."""
    token = _run_id.set(run_id)
    try:
        yield
    finally:
        _run_id.reset(token)


@dataclass(frozen=True)
class TraceHandle:
    """The current trace position and run binding, to continue on another thread."""

    context: Context
    run_id: str | None


def capture() -> TraceHandle:
    """Capture where we are, so a server thread (relay, MCP) can open child spans here."""
    return TraceHandle(otel_context.get_current(), _run_id.get())


@contextmanager
def restore(handle: TraceHandle | None) -> Iterator[None]:
    """Make ``handle`` the current trace position (and run) for this block; no-op for None."""
    if handle is None:
        yield
        return
    token = otel_context.attach(handle.context)
    run_token = _run_id.set(handle.run_id)
    try:
        yield
    finally:
        _run_id.reset(run_token)
        otel_context.detach(token)


@contextmanager
def span(name: str, kind: SpanKind, /, **attrs: object) -> Iterator[Span]:
    """Open one span for a boundary crossing; record its outcome; re-raise any exception.

    Dotted OpenInference keys are passed by unpacking, e.g. ``**{"input.value": prompt}``.
    """
    tracer = _provider.get_tracer(_TRACER_NAME) if _provider else trace.get_tracer(_TRACER_NAME)
    with tracer.start_as_current_span(
        name, record_exception=False, set_status_on_exception=False
    ) as current:
        current.set_attribute(KIND_ATTRIBUTE, kind.value)
        run_id = _run_id.get()
        if run_id is not None:
            current.set_attribute("session.id", run_id)
            current.set_attribute("episalpha.run_id", run_id)
        annotate(current, **attrs)
        try:
            yield current
        except BaseException as error:
            # Class and error code only: exception text can carry response bodies, URLs with
            # query-string keys, or other content that must never reach the JSONL fallback.
            current.set_attribute("outcome", type(error).__name__)
            code = getattr(error, "code", None)
            summary = type(error).__name__
            if isinstance(code, StrEnum):
                summary = f"{summary}: {code.value}"
            current.set_status(Status(StatusCode.ERROR, summary))
            raise
        current.set_attribute("outcome", "ok")


def event(name: str, /, **fields: object) -> None:
    """Add a span event to the current span; a no-op when no span is recording."""
    current = trace.get_current_span()
    if current.is_recording():
        current.add_event(name, _attributes(fields))


def trace_id_hex(target: Span) -> str:
    return f"{target.get_span_context().trace_id:032x}"


def trace_url(trace_id: str) -> str | None:
    """A link to the trace in the local Phoenix UI, or ``None`` when Phoenix is not configured."""
    if _config is None or _config.otlp_endpoint is None:
        return None
    base = _config.otlp_endpoint.removesuffix("/v1/traces").rstrip("/")
    return f"{base}/redirects/traces/{trace_id}"
