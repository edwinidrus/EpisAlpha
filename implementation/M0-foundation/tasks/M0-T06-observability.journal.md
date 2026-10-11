# M0-T06 journal

## Attempt 1 — 2026-10-10 22:30 UTC — claude-opus-5-5
- Hypothesis: a thin module over the OpenTelemetry SDK can give every boundary a redacted span,
  with a metadata-only JSONL fallback and an optional loopback-only OTLP exporter, without
  relaxing strict mypy.
- Verify:
  - `uv add opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp-proto-http` ->
    opentelemetry-api 1.45.1, opentelemetry-sdk 1.45.1, opentelemetry-exporter-otlp-proto-http
    1.45.1, protobuf 7.36.2 (plus requests, urllib3, googleapis-common-protos as transitive
    dependencies). Python 3.12 OK. Bounds pinned `>=1.45,<2.0`.
  - Imports checked: `opentelemetry.sdk.trace.export.in_memory_span_exporter.InMemorySpanExporter`,
    `opentelemetry.sdk.trace.export.BatchSpanProcessor`,
    `opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter`.
    `ReadableSpan.__init__(name, context, parent, resource, attributes, events, links, kind,
    instrumentation_info, status, start_time, end_time, instrumentation_scope)` inspected.
  - Baseline: four checks green, 324 passed (after M0-T05).
  - Red first: `uv run pytest -q tests/observability` -> `ModuleNotFoundError: No module named
    'episalpha.observability'`.
- Did:
  - `src/episalpha/observability.py` (new): `SpanKind`, `span`, `event`, `annotate`,
    `bind_run`, `trace_id_hex`, `trace_url`, `configure_tracing`, `shutdown_tracing`,
    `active_exporters`, `RedactionSpanProcessor`, `MetadataOnlyExporter`, `JsonlSpanExporter`.
  - `src/episalpha/settings.py`: `ObservabilityConfig` (loopback-only `otlp_endpoint`,
    `capture_content`, `service_name`, `project_name`, `sample_ratio`,
    `export_timeout_seconds`) on `Settings.observability`.
  - `config/demo.example.toml`, `config/demo.toml`: `[observability]` section, endpoint
    commented out.
  - `pyproject.toml`, `uv.lock`: the three OpenTelemetry packages.
  - `tests/observability/test_observability.py`: 17 tests.
  - `tests/conftest.py`: autouse network guard for the default suite (connect, connect_ex and
    getaddrinfo outside loopback fail; `live` tests exempt). Outside the pack's file list, but
    the pack's acceptance requires a socket guard for the whole default suite, and conftest is
    the only place that covers it.
- Decisions:
  - Module-level provider instead of the OpenTelemetry global provider (settable once per
    process); `shutdown_tracing()` resets it. Marked `ponytail:` in the code.
  - Redaction wraps the downstream processors and rebuilds the finished span, so every
    exporter sees only the redacted copy. The JSONL path and `capture_content = false` reuse
    one `MetadataOnlyExporter` that swaps content keys for `<key>_hash` / `<key>_bytes`.
  - A `NullHandler` on the `opentelemetry` logger keeps export failures off stderr.
  - Added `export_timeout_seconds` (default 5) so an absent Phoenix cannot stall a flush for the
    SDK default.
  - `trace_url` builds `<base>/redirects/traces/<trace_id>`. That Phoenix route is UNVERIFIED
    here and is checked against the live container in M0-T07.
- Ran:
  - `uv run pytest -q tests/observability tests/contracts/test_settings.py` -> `57 passed`
  - ruff -> All checks passed; format -> 38 files already formatted; mypy -> `Success: no
    issues found in 21 source files` (one `dict(item.attributes)` arg-type error fixed with
    `or {}`; no ignores); `pytest -m "not live"` -> `341 passed, 2 deselected`.
- Sample `spans.jsonl` line (synthetic; content replaced by hash and size):
  `{"name": "tool.search_evidence", "trace_id": "0dee9c68176cab8a1dccd77e42843c5c", "span_id":
  "6b95c50619d43b9a", "parent_span_id": null, "kind": "RETRIEVER", "start":
  "2026-10-10T22:34:52.669844+00:00", "end": "2026-10-10T22:34:52.669940+00:00",
  "duration_ms": 0.096, "status": "UNSET", "status_message": null, "attributes":
  {"openinference.span.kind": "RETRIEVER", "session.id": "run_sample", "episalpha.run_id":
  "run_sample", "input.value_hash": "509563cb…bf0b", "input.value_bytes": 15, "hits": 2,
  "outcome": "ok"}, "events": [{"name": "validation.check", "time": "…", "attributes":
  {"check": "claim_references", "passed": true}}], "service": "episalpha"}`
- Outcome: PASS
