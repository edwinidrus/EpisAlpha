# M2 plan: evidence storage, connectors and snapshots

**Goal:** source-linked, effectively immutable inputs exist before Hermes reasons over them.
Numeric fundamentals arrive point-in-time, and every connector call is observable.

**Plan source:** plan §8 (M2-T01..T04), §3.5, §2.6; amendments A2, A4, A6, A8, A11.

## Tasks

| Task | Title | Status | Depends on | Pack |
|---|---|---|---|---|
| M2-T01 | SQLite persistence and migration | DONE | G1 | — |
| M2-T02 | Content-addressed payloads and exact spans | DONE | M2-T01 | — |
| M2-T03 | Narrow source adapters | DONE | M2-T02 | — |
| M2-T04 | Frozen snapshot builder and demo corpus | DONE | M2-T03 | — |
| M2-T05 | Point-in-time XBRL fundamentals (A8) | TODO | M2-T03, M1-T05 | [pack](tasks/M2-T05-xbrl.md) |
| M2-T06 | Instrument connectors with events (A11) | TODO | M0-T06, M2-T05 | [pack](tasks/M2-T06-connector-events.md) |

## Scope

- **In:**
  - `connectors/xbrl.py`.
  - Events in `connectors/prices.py`, `connectors/filings.py` and `connectors/xbrl.py`.
- **Out:**
  - Snapshot and validation events. The M4-T01 runner emits these at the orchestration point,
    which keeps `snapshots.py` and `validation.py` pure.
  - Live ingestion of the three real cases (owner checkpoint, below).

## Owner checkpoint (outstanding since G2)

The three real cases (LULU, TSCO, CALX) have not been ingested from live SEC payloads, and their
key quotations have not been inspected by hand. The case mapping stays **PROVISIONAL** until
then. That check needs live SEC fetches and owner review, and it must be done before M4-T04
(real thesis quality review).

## Existing interfaces (seen 2026-10-10)

| Name | Location |
|---|---|
| `ALLOWED_HOSTS` (includes `data.sec.gov`), `user_agent`, `check_allowed` | `src/episalpha/connectors/filings.py:38-58` |
| `SecEdgarFilings` (`ingest`, `fetch`, `parse_submissions`, which returns `FilingMetadata` with `acceptance_datetime`) | `filings.py:82-215` |
| `SourceError`, `Transport`, `AdjustmentBasis`, `PriceSeries` | `src/episalpha/connectors/prices.py:39-112` |
| `ObjectStore.put/get` | `src/episalpha/storage/objects.py:33-94` |
| `extract_text`, `make_span`, `find_span`, `PARSER_VERSION` | `src/episalpha/evidence/parsing.py` |
| `eligibility_time`, `is_eligible`, `select_current_versions` | `src/episalpha/evidence/temporal.py:23-88` |
| `ErrorCode` (`NO_DATA`, `SOURCE_FAILED`, …) | `src/episalpha/contracts/errors.py:12` |
