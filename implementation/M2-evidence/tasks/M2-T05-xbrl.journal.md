# M2-T05 journal

## Attempt 1 — 2026-10-10 23:05 UTC — claude-opus-5-5
- Owner approval: public SEC GETs approved for the unattended session (2026-10-10). The SEC
  fair-access User-Agent carried the owner's contact email; it is not written into any repo file.
- Verify:
  - Live fetch, once: `GET https://data.sec.gov/api/xbrl/companyfacts/CIK0001397187.json` ->
    `200 2968163` bytes, SHA-256
    `89f7c4fd2ad8016bb521a2a2999da6515819d628d61ea81c773d838ba2addfaf`. Top-level keys `cik`,
    `entityName`, `facts`; taxonomies `dei`, `us-gaap`, `srt`, `ecd`, `ffd`; 419 us-gaap
    concepts; 20,022 facts in total.
  - **Field names verified against the real payload:** `accn, end, filed, form, fp, frame, fy,
    start, val`. They match the third-party description. `frame` is present only on some
    facts, and `start` only on duration facts.
  - Live fetch, once: `GET https://data.sec.gov/submissions/CIK0001397187.json` -> `200 172234`,
    SHA-256 `5accc16a94637817d562cb0c5e8778e9dbe6f48dc0c993a90860a80d0a51a10c`, 1,002 recent
    filings with `acceptanceDateTime`.
  - `grep -n acceptance_datetime src/episalpha/connectors/filings.py` -> `FilingMetadata.
    acceptance_datetime: UtcTimestamp | None`, filled by `parse_submissions`.
  - 350 restated groups exist in LULU's payload (same period, different value, different
    accession). The fixture uses `AccruedLiabilitiesCurrent` at instant 2021-01-31:
    - `0001397187-21-000018` 10-Q filed 2021-06-03, accepted 2021-06-04T00:18:14Z, val 211911000
    - `0001397187-21-000027` 10-Q, accepted 2021-09-09T00:17:32Z, val 211911000
    - `0001397187-21-000039` 10-Q, accepted 2021-12-10T02:16:32Z, val 211911000
    - `0001397187-22-000014` 10-K filed 2022-03-29, accepted 2022-03-30T00:16:02Z, val
      **226867000** (the restatement)
    plus two revenue facts for 2025-05-05..2025-08-03 (accessions -25-000039 and -26-000127).
    The fixture is 1,982 bytes and reproduces SEC's own byte formatting for every fact
    (asserted when the fixture was cut). The full payload is not committed.
  - Baseline: four checks green, 370 passed.
  - Red first: `uv run pytest -q tests/evidence/test_xbrl.py` -> `ImportError: cannot import
    name 'xbrl' from 'episalpha.connectors'`.
- Decisions:
  - **Fact-level documents.** Today's companyfacts payload is a first capture, so as one document
    it would be ineligible for every historical cutoff. Each selected fact therefore becomes its
    own `EvidenceDocument` version: `provider_verified` at its accession's acceptance time,
    `first_capture` when acceptance is unknown. The payload is the preserved companyfacts
    bytes, and the span is the fact's exact JSON object. Every filing of one (concept, unit,
    period) shares one `source_family_id`, so `select_current_versions` treats a restatement as
    a later version (tested).
  - **`accounting_basis` is the taxonomy (`us-gaap`), not `form + fp`** as the pack suggested.
    Form + fiscal period is filing metadata; using it would make every cross-period derivation
    fail M1-T05's same-basis rule. Form, fiscal period, fiscal year, accession and filed date go
    into `source_context`.
  - An unknown concept is `NO_DATA` (raised). A known concept with nothing eligible at the
    cutoff returns `None`; callers map that to `INELIGIBLE_EVIDENCE`, not `NO_DATA`.
  - The CIK is validated as 10 digits before any URL is built (`INVALID_REQUEST`).
- Observation for the owner: EDGAR `acceptanceDateTime` values carry a `Z` suffix, and the
  existing M2-T03 code treats them as UTC (for example 2021-06-04T00:18:14Z for a filing dated
  2021-06-03). If EDGAR actually means Eastern time, availability would be 4–5 hours earlier
  than recorded. That is conservative for eligibility, but worth confirming.
- Did: `src/episalpha/connectors/xbrl.py`, `tests/fixtures/connectors/companyfacts_lulu.json`,
  `tests/evidence/test_xbrl.py` (20 tests).
- Ran:
  - `uv run pytest -q tests/evidence/test_xbrl.py` -> `20 passed`
  - Full real payload: `20022 facts parsed in 0.19 s; located 300 / 300 random facts exactly`
  - Four checks: All checks passed; formatted; no issues in 23 source files; `390 passed`.
- Outcome: PASS
