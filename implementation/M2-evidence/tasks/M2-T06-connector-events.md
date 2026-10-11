# M2-T06 — Instrument connectors with spans (A11, A14)

| Field | Value |
|---|---|
| Status | DONE |
| Depends on | M0-T06, M2-T05 |
| Phase constitution | [../CONSTITUTION.md](../CONSTITUTION.md) (inherits [global](../../CONSTITUTION.md)) |
| Plan source | amendments A11 and A14 |
| Journal | `tasks/M2-T06-connector-events.journal.md` |

## 0. Context to load

Load these and nothing else:
- `implementation/CONSTITUTION.md`, §VII (the span table and content policy)
- `implementation/M2-evidence/CONSTITUTION.md`, article 10
- `src/episalpha/observability.py` (M0-T06): `span`, `event`, `SpanKind`
- The sample `spans.jsonl` line in `implementation/M0-foundation/tasks/M0-T06-observability.journal.md`
- `src/episalpha/connectors/prices.py`, `filings.py` and `xbrl.py`, the fetch and refusal paths
  only
- `tests/evidence/test_connectors.py`, the transport fakes

## 1. Plan

- **Goal:** every external call a connector makes is one `connector.fetch` span (`CHAIN`) with
  a clear outcome. A failing source can then be diagnosed in Phoenix or in `spans.jsonl`
  without re-running.
- **Files:**
  - Modify `src/episalpha/connectors/prices.py`, `src/episalpha/connectors/filings.py` and
    `src/episalpha/connectors/xbrl.py`.
  - Focused test: `tests/evidence/test_connector_events.py`.
- **Span attributes:**

  | Attribute | Value |
  |---|---|
  | `episalpha.source_id` | `sec_edgar`, `sec_xbrl` or `alpha_vantage` |
  | `episalpha.operation` | `daily`, `fetch` or `companyfacts` |
  | `server.address` | the host only |
  | `http.response.status_code` | when there is one |
  | `episalpha.outcome` | `ok`, `NO_DATA` or `SOURCE_FAILED` |
  | `episalpha.bytes`, `episalpha.payload_hash` | when stored |

  Errors also set the span error status, with the error code as the message.
- **Content policy:** connectors put **no content** on spans. Never record the body, the query
  string, or the full URL (Alpha Vantage carries `apikey` in its query). Payloads are already
  canonical in the object store, referenced by hash.
- **Out of scope:**
  - Snapshot and validation spans (M4-T01, at orchestration).
  - Changing any error semantics.
  - Retry logic.
- **Do not:** change any existing test's expectations.

## 2. Verify (before building)

- [ ] `episalpha.observability.span` exists and the test-only in-memory exporter hook works, as
      the M0-T06 journal shows.
- [ ] Each connector's single transport call site is identified (`grep -n "self.transport"`).
      Journal the line numbers.
- [ ] Baseline: the four standard checks are green.
- [ ] **Red first.** Write `tests/evidence/test_connector_events.py` with the in-memory exporter.
      Cover:
  - Success gives one span with `outcome=ok`, plus bytes and hash.
  - An Alpha Vantage `Information` throttle gives `outcome=SOURCE_FAILED` with error status.
  - Empty data gives `outcome=NO_DATA`.
  - The Alpha Vantage key value, set through `monkeypatch`, appears in no attribute, event or
    status message.
  - No URL query string is recorded.
  - Exactly one span per call.

## 3. Build

1. Wrap the single transport call site per connector in
   `span("connector.fetch", SpanKind.CHAIN, ...)`.
2. Set the outcome where `SourceError` is raised, or in one wrapper. Choose whichever adds fewer
   lines and journal the choice.

## 4. Test

```bash
uv run pytest -q tests/evidence
uv run ruff check . && uv run ruff format --check . && uv run mypy src/episalpha && uv run pytest -q -m "not live"
```

Acceptance:
- [ ] All three connectors emit `connector.fetch` spans as specified.
- [ ] No secret, body or query string in any span.
- [ ] Every existing test in `tests/evidence` is unchanged and green.

## 5. Diagnose

- [ ] `uv run python scripts/diagnose.py`: no regression.
- [ ] Paste three sample `spans.jsonl` lines into the journal (success, throttle, empty). If
      Phoenix (M0-T07) is running, also record that the spans appear there.
- [ ] Re-run G2 and append the result to `../GATE.md`.

## 6. Stop and hand off

- **BLOCKED if:** instrumenting would change a connector's public signature. In that case,
  report the reason rather than reshaping the API.
- **Record:** M2 `PROGRESS.md`, `STATUS.md`, and the journal.
- **Next:** M3-T01.
