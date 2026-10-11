# M0-T06 — OpenTelemetry observability foundation (A11, A14)

| Field | Value |
|---|---|
| Status | DONE |
| Depends on | M0-T02 |
| Phase constitution | [../CONSTITUTION.md](../CONSTITUTION.md) (inherits [global](../../CONSTITUTION.md)) |
| Plan source | amendments A11 and A14 |
| Journal | `tasks/M0-T06-observability.journal.md` |
| New dependencies | `opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-http`. Owner approved through A14 on 2026-10-10. |

## 0. Context to load

Load these and nothing else:
- `implementation/CONSTITUTION.md`, §VI (secrets) and §VII (observability: span table, content
  policy)
- `implementation/M0-foundation/CONSTITUTION.md`, article 6
- `src/episalpha/settings.py`:
  - `PathsConfig` (`:77-91`, `settings.paths.data_root`)
  - `ProviderRoute.credential()` (`:109`)
  - `SourceConfig.credential()` (`:189`)
  - `Settings` (`:310`)
  - `load_settings` (`:347`)
- `config/demo.example.toml`
- `tests/contracts/test_settings.py`, the house test style

> Every boundary emits one OpenTelemetry span through `episalpha.observability`. The **local
> Phoenix exporter** receives full content; the **JSONL fallback** receives metadata only. A
> `RedactionSpanProcessor` strips every resolved credential value **before any exporter**.
> Phoenix outage never fails a run. (global constitution, articles 27–29)

## 1. Plan

- **Goal:** one small module through which the whole system emits correlated, redacted
  OpenTelemetry spans. They always go to a local JSONL file, and to a local Phoenix as well when
  one is configured. Spans are never canonical state.
- **Files:**
  - `src/episalpha/observability.py` (new)
  - `src/episalpha/settings.py`. Add `ObservabilityConfig`, with fields and defaults:
    - `otlp_endpoint: str | None = None`, for example `http://127.0.0.1:6006/v1/traces`. It must
      be loopback (`127.0.0.1`, `localhost` or `::1`), otherwise validation fails.
    - `capture_content: bool = True`. This applies to the OTLP exporter only.
    - `service_name: str = "episalpha"`
    - `project_name: str = "episalpha"`. This becomes the Phoenix project, sent through the
      `openinference.project.name` resource attribute.
    - `sample_ratio: float`, between 0 and 1, default 1.0. It is the only float in settings, and
      it is not a financial value.
  - `config/demo.example.toml`, with a commented `[observability]` section.
  - `pyproject.toml` / `uv.lock`, adding the three OpenTelemetry packages.
  - Focused test: `tests/observability/test_observability.py`
- **Produces, in `observability.py`:**
  - `SpanKind` constants for the OpenInference kinds used (`CHAIN`, `LLM`, `TOOL`,
    `RETRIEVER`, `AGENT`, `EVALUATOR`), set as attribute `openinference.span.kind`.
  - `configure_tracing(settings) -> TracerProvider`. It is idempotent: a second call returns
    the same provider and adds no processors. It installs:
    1. the `RedactionSpanProcessor`, which wraps the exporters below;
    2. a `BatchSpanProcessor` around a `JsonlSpanExporter` writing
       `<data_root>/logs/spans.jsonl`. **Content attributes are dropped here.** The dropped keys
       are `input.value`, `output.value`, `llm.input_messages*`, `llm.output_messages*`,
       `tool.parameters` and `retrieval.documents*`. A `*_hash` and `*_bytes` pair is kept in
       their place.
    3. **only if** `otlp_endpoint` is set: a `BatchSpanProcessor` around the
       `OTLPSpanExporter(endpoint=...)`. It carries content only when `capture_content` is true.
  - `span(name, kind, /, **attrs)`, a context manager that does four things:
    - starts a span on the module tracer;
    - sets `kind` and the attributes;
    - on exit, records `outcome` (`ok`, or the exception class), sets an error status, and
      re-raises;
    - returns the span so a caller can add attributes.
  - `event(name, /, **fields)`, which adds a span event to the current span. It is a no-op when
    no span is active.
  - `bind_run(run_id)`, which sets `session.id` and `episalpha.run_id` on spans created in the
    context.
  - `trace_id_hex(span) -> str` and `trace_url(trace_id) -> str | None`. The URL is built only
    when an endpoint is configured; it is used by the M4 CLI and the M5 UI.
  - `RedactionSpanProcessor(secrets)`. It is built from every resolved credential: the provider
    and all sources. It replaces each occurrence with `***` in string attributes, event
    attributes and the status message, recursively through sequences.
- **Value conversion:** `Decimal` to `str`; `datetime` to ISO with offset; `Path` to `str`;
  other types to `repr()`, truncated to 2,000 characters for content attributes and 200 for
  others.
- **Out of scope:**
  - The Phoenix container (M0-T07).
  - Instrumenting existing modules (M2-T06 and later packs).
  - Metrics and logs signals. Traces only.
- **Do not:**
  - Send to any non-loopback endpoint.
  - Write to stdout or stderr. That would pollute the CLI in M4.
  - Let any exporter error propagate to the caller.
  - Read spans back in application logic.
  - Relax strict mypy globally. If the OpenTelemetry stubs are incomplete, add narrow
    per-line ignores in this module only.

## 2. Verify (before building)

- [ ] Check the dependencies resolve. Run `uv add opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp-proto-http`,
      then journal the locked versions and confirm Python 3.12 compatibility.
- [ ] Check the installed SDK provides `InMemorySpanExporter`, `BatchSpanProcessor`, and
      `OTLPSpanExporter` from the `opentelemetry.exporter.otlp.proto.http.trace_exporter` path.
      Journal the import lines.
- [ ] Baseline: the four standard checks are green.
- [ ] **Red first.** Write the tests. They use an `InMemorySpanExporter` injected via a test-only
      hook, `tmp_path`, and a credential set with `monkeypatch.setenv("TEST_SECRET", "s3cr3t-value")`.
      They fail before the module exists. Cover:
  - Span nesting produces one trace (parent and child IDs).
  - `bind_run` sets `session.id` on child spans.
  - An exception inside `span()` sets an error status and `outcome`, and re-raises.
  - The secret, placed in an attribute, an event and a nested sequence, appears **nowhere** in
    either exporter's output. Grep the JSONL file text.
  - The JSONL file contains no `input.value` or `output.value`, but has `*_hash` and `*_bytes`.
  - With `otlp_endpoint=None` there is no OTLP processor.
  - An OTLP exporter pointed at an unreachable loopback port: `span()` still returns normally,
    and the JSONL still gets the span.
  - A non-loopback `otlp_endpoint` fails settings validation.
  - `configure_tracing` called twice gives the same provider, with no duplicate processors.
  - The default test suite performs no network I/O. A socket guard fixture fails on any
    `connect` outside loopback.

## 3. Build

1. Write `ObservabilityConfig` and its validators in `settings.py`, and the example TOML
   section.
2. Write the redaction processor and the content-dropping JSONL exporter.
3. Write `configure_tracing`, `span`, `event`, `bind_run`, `trace_url`.

## 4. Test

```bash
uv run pytest -q tests/observability tests/contracts/test_settings.py
uv run ruff check . && uv run ruff format --check . && uv run mypy src/episalpha && uv run pytest -q -m "not live"
```

Acceptance:
- [ ] Every test listed under Verify passes.
- [ ] Strict mypy is clean.
- [ ] Redaction is proven for both exporters.
- [ ] The default suite stays offline.
- [ ] An exporter failure never reaches the caller.
- [ ] A missing Phoenix degrades to JSONL only.
- [ ] The only new dependencies are the three OpenTelemetry packages, recorded with versions.

## 5. Diagnose

- [ ] `uv run python scripts/diagnose.py`: the test count rises, and there is no regression.
- [ ] Paste one sample `spans.jsonl` line into the journal (synthetic, no secret, no content) as
      the reference format.
- [ ] Journal entry written.

## 6. Stop and hand off

- **BLOCKED if:**
  - an OpenTelemetry package conflicts with the lock;
  - strict mypy cannot pass without a global relaxation.
- **Record:** M0 `PROGRESS.md`, `STATUS.md`, and the journal.
- **Next:** M0-T07.
