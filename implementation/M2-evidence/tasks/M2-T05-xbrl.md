# M2-T05 — Point-in-time XBRL fundamentals (A8)

| Field | Value |
|---|---|
| Status | DONE |
| Depends on | M2-T03, M1-T05 |
| Phase constitution | [../CONSTITUTION.md](../CONSTITUTION.md) (inherits [global](../../CONSTITUTION.md)) |
| Plan source | plan §1.2 "Numeric fundamentals" row, §3.5, M2-T05 card; amendment A8 |
| Journal | `tasks/M2-T05-xbrl.journal.md` |

## 0. Context to load

Load these and nothing else:
- `implementation/CONSTITUTION.md`
- `implementation/M2-evidence/CONSTITUTION.md`, articles 1–4 and 6–9
- [../PLAN.md](../PLAN.md), the interface table
- `src/episalpha/connectors/filings.py` (house style, `ALLOWED_HOSTS`, `SecEdgarFilings`)
- `src/episalpha/connectors/prices.py:39-60` (`SourceError`, `Transport`)
- `src/episalpha/evidence/temporal.py`
- `src/episalpha/evidence/parsing.py` (`make_span`, `find_span`)
- `src/episalpha/contracts/knowledge.py:203-290` (`EvidenceDocument`, `EvidenceSpan`,
  `NumericFact`, `Claim`)
- `tests/evidence/test_connectors.py`, the house test style and transport fakes

> SEC `companyfacts` API, `primary`, no key, same User-Agent and host allowlist as
> `sec_edgar`. Facts are selected by `filed <= cutoff`; the `frames` API is **never** used for a
> historical cutoff because it returns the last-filed (possibly restated) value. (plan §1.2, A8)

Facts about the SEC API, observed in SEC docs on 2026-10-10:
- `https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json` returns all concepts for one
  company. No key; no CORS.
- `frames` "aggregates one fact per reporting entity … last filed". It is **forbidden here**.
- Field names per fact (`start`, `end`, `val`, `accn`, `fy`, `fp`, `form`, `filed`, `frame`)
  come from third-party descriptions, **not** SEC docs. **Verify them against a real payload**
  before coding.

## 1. Plan

- **Goal:** for a concept such as `us-gaap:Revenues` and a research cutoff, return the value
  that was publicly available at that cutoff. Return it as a `NumericFact` on a `reported` claim
  candidate, citing an exact span of the preserved payload.
- **Files:**
  - `src/episalpha/connectors/xbrl.py` (new)
  - `tests/fixtures/connectors/companyfacts_*.json`
  - Focused test: `tests/evidence/test_xbrl.py`
- **Produces:**
  - `class XbrlFact(Contract)`, with fields `taxonomy`, `concept`, `unit`, `start: date | None`,
    `end: date`, `value: DecimalString`, `accession`, `form`, `filed: date`, `fy`, `fp`.
  - `class SecXbrlFacts`, with `source_id = "sec_xbrl"`. Its constructor follows the
    `SecEdgarFilings` constructor style. Methods:
    - `fetch_companyfacts(cik) -> bytes`
    - `parse(body) -> list[XbrlFact]`
    - `select_as_of(facts, concept, unit, period, availability: Mapping[accession, datetime | None], cutoff) -> XbrlFact | None`
    - `to_numeric_fact(fact) -> NumericFact`
- **The eligibility rule, and the crux of this task:**
  - A fact's availability is the **acceptance datetime of its accession**. That comes from the
    submissions data that `SecEdgarFilings.parse_submissions` already returns
    (`FilingMetadata.acceptance_datetime`) and is passed in as `availability`.
  - When the acceptance datetime is unknown, the fact is **not eligible for a historical
    cutoff**. Only first capture counts (constitution article 3).
  - The `filed` date alone never qualifies a fact.
  - Among eligible facts for the same (concept, unit, period), the latest-accepted one wins, so
    the restatement rule matches `select_current_versions`.
- **Spans.** Store the raw companyfacts bytes through `ObjectStore`. The span quote is the exact
  JSON object text of the selected fact, located with `find_span` over the extracted text. If
  JSON normalization makes exact location impossible, **stop and report BLOCKED** with the
  evidence. The owner alternative is to cite the 10-Q/10-K HTML span instead.
- **Errors:**
  - Transport failure, a non-JSON body, or a body without `facts` is `SOURCE_FAILED`.
  - An unknown concept, or no eligible fact, is `NO_DATA`.
  - A non-allowlisted host is `NOT_AUTHORIZED`, through `check_allowed`.
- **Out of scope:**
  - The `frames` API, at any time.
  - Any form or computation beyond selecting the fact.
  - Turning facts into theses.
  - Logging (M2-T06).
- **Do not:**
  - Add a dependency (stdlib `json`).
  - Parse `val` through a float. Use `Decimal(str(...))` at the JSON boundary, or load with
    `parse_float=Decimal`.

## 2. Verify (before building)

- [ ] **Owner approval** for one live fetch, or reuse an already-captured payload. Fetch
      `companyfacts/CIK0001397187.json` (LULU) once, with the SEC User-Agent. Journal the size
      and SHA-256, and the observed per-fact keys. Cut a small fixture: 2 concepts, including
      one restated value (the same period with two different `accn`). Never commit the full
      payload.
- [ ] `parse_submissions` returns `acceptance_datetime` per accession, as the journal shows
      (`grep -n acceptance_datetime src/episalpha/connectors/filings.py`).
- [ ] Baseline: the four standard checks are green.
- [ ] **Red first.** Write `tests/evidence/test_xbrl.py` so it fails before `xbrl.py` exists.
      Cover:
  - Parse.
  - Decimal fidelity: `val` `1234567.89` survives exactly.
  - As-of selection: original accepted at T1, restatement accepted at T3. A query at T2 returns
    the original; a query at T4 returns the restatement.
  - Unknown availability is ineligible.
  - Malformed JSON is `SOURCE_FAILED`; an unknown concept is `NO_DATA`.
  - The host allowlist.
  - The span quote equals the stored-text slice.
  - A test asserts no code path builds a `frames` URL (grep the module source).

## 3. Build

1. Write `XbrlFact` and `parse`, with the Decimal-preserving load.
2. Write `select_as_of`, as a pure function.
3. Write `fetch_companyfacts`, reusing `check_allowed` and `user_agent` from `filings.py`.
4. Write `to_numeric_fact`:
   - `metric = "<taxonomy>:<concept>"`
   - `unit` from the fact
   - the period from `start`/`end`; for an instant fact, `start == end`
   - `accounting_basis = form + fp`
   - `source_context = accession`
5. Write the span helper on the stored text.

## 4. Test

```bash
uv run pytest -q tests/evidence/test_xbrl.py
uv run ruff check . && uv run ruff format --check . && uv run mypy src/episalpha && uv run pytest -q -m "not live"
```

Acceptance:
- [ ] A restatement filed after the cutoff is never selected.
- [ ] The `frames` API is never called.
- [ ] A refusal maps to `SOURCE_FAILED` and missing data to `NO_DATA`.
- [ ] The injected transport keeps the default suite offline.
- [ ] The output `NumericFact` validates. A derived claim built on two such facts passes
      M1-T05 recomputation (one integration test).
- [ ] No floats.

## 5. Diagnose

- [ ] `uv run python scripts/diagnose.py`: no regression; `tests/evidence` grows.
- [ ] The journal records the verified field names (the real payload versus the third-party
      claim) and the restatement fixture's two accessions.

## 6. Stop and hand off

- **BLOCKED if:**
  - the owner has not approved the live fetch and no captured payload exists;
  - field names differ materially from the plan;
  - exact span location is impossible.
- **Record:** M2 `PROGRESS.md`, `STATUS.md`, and the journal.
- **Next:** M2-T06.
