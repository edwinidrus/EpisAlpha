# M2-T06 — Instrument connectors with events (A11)

| Field | Value |
|---|---|
| Status | TODO |
| Depends on | M0-T06, M2-T05 |
| Phase constitution | [../CONSTITUTION.md](../CONSTITUTION.md) (inherits [global](../../CONSTITUTION.md)) |
| Plan source | amendment A11 |
| Journal | `tasks/M2-T06-connector-events.journal.md` |

## 0. Context to load

Load these and nothing else:
- `implementation/CONSTITUTION.md`, articles 26–30
- `implementation/M2-evidence/CONSTITUTION.md`, article 10
- `src/episalpha/observability.py` (from M0-T06): `EventName`, `event`, `timed`
- The sample event line in `implementation/M0-foundation/tasks/M0-T06-observability.journal.md`
- `src/episalpha/connectors/prices.py`, `filings.py` and `xbrl.py`, the fetch and refusal paths
  only
- `tests/evidence/test_connectors.py`, the transport fakes

## 1. Plan

- **Goal:** every external call a connector makes leaves exactly one structured, redacted
  outcome event. A failing source can then be diagnosed from the log alone, without
  re-running.
- **Files:**
  - Modify `src/episalpha/connectors/prices.py`, `src/episalpha/connectors/filings.py` and
    `src/episalpha/connectors/xbrl.py`.
  - Focused test: `tests/evidence/test_connector_events.py`.
- **Events:**

  | Event | When | Fields |
  |---|---|---|
  | `connector.request` | before the transport call | `source_id`, `host`, `operation` (`daily`, `fetch`, `companyfacts`) |
  | `connector.response` | success | `source_id`, `bytes`, `payload_hash` (when stored), `duration_ms` |
  | `connector.refused` | any `SourceError` raised | `source_id`, `error_code`, `reason` (the error message, truncated to 200 characters), `duration_ms` |

- **Out of scope:**
  - Snapshot and validation events (M4-T01, at orchestration).
  - Changing any error semantics.
  - Retry logic.
- **Do not:**
  - Log the response body, query parameters that carry an API key (Alpha Vantage `apikey`), or
    the full URL with its query. Log the host only.
  - Change any existing test's expectations.

## 2. Verify (before building)

- [ ] `episalpha.observability` exists with `EventName.CONNECTOR_*` members
      (`grep -n "connector" src/episalpha/observability.py`).
- [ ] Each connector's single transport call site is identified (`grep -n "self.transport"`).
      Journal the line numbers.
- [ ] Baseline: the four standard checks are green.
- [ ] **Red first.** Write `tests/evidence/test_connector_events.py`. It captures records with
      a `logging.Handler` attached to the `episalpha` logger, or with
      `configure_logging(tmp settings)` reading the file. Cover:
  - Success emits request and response.
  - A throttle (Alpha Vantage `Information`) emits request and refused, with
    `error_code=SOURCE_FAILED`.
  - Empty data emits refused with `NO_DATA`.
  - The Alpha Vantage key value (set through `monkeypatch`) never appears in any record.
  - Exactly one outcome event per call.

## 3. Build

1. Wrap each transport call in `timed(...)`, or add explicit `event()` calls, at the single call
   site per connector.
2. Emit `connector.refused` at the point where `SourceError` is raised, or in one wrapper that
   catches, emits and re-raises. Choose whichever adds fewer lines and record the choice in the
   journal.

## 4. Test

```bash
uv run pytest -q tests/evidence
uv run ruff check . && uv run ruff format --check . && uv run mypy src/episalpha && uv run pytest -q -m "not live"
```

Acceptance:
- [ ] The three connectors emit the event triple as specified.
- [ ] No secret and no body in any record.
- [ ] Every existing test in `tests/evidence` is unchanged and green.

## 5. Diagnose

- [ ] `uv run python scripts/diagnose.py`: no regression.
- [ ] Paste three sample lines into the journal (success, throttle, empty).
- [ ] Re-run G2 and append the result to `../GATE.md`.

## 6. Stop and hand off

- **BLOCKED if:** instrumenting would change a connector's public signature. In that case,
  report the reason rather than reshaping the API.
- **Record:** M2 `PROGRESS.md`, `STATUS.md`, and the journal.
- **Next:** M3-T01.
