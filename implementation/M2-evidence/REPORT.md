# M2 phase report: evidence storage, connectors and snapshots

**Gate G2: PASSED on 2026-10-10** (re-run after amendments A8, A11 and A14). The owner
checkpoint is still open: live ingestion of the three real cases, with their key quotations
inspected by hand. Real output is in [PROGRESS.md](PROGRESS.md), [GATE.md](GATE.md) and the
journals.

## What M2 delivers

| Task | Status | What exists now |
|---|---|---|
| M2-T01 | DONE (2026-09-20) | SQLite (WAL, foreign keys, busy timeout), versioned assessments, idempotent run admission, FTS5 over spans |
| M2-T02 | DONE (2026-09-20) | Content-addressed object store; deterministic text normalization; exact spans |
| M2-T03 | DONE (2026-09-20) | Alpha Vantage prices and SEC EDGAR filings over an injected transport |
| M2-T04 | DONE (2026-09-20) | Frozen snapshot builder; 3 real case manifests (PROVISIONAL), 5 synthetic adversarial cases |
| **M2-T05** | **DONE (2026-10-10)** | **Point-in-time XBRL facts (A8)** |
| **M2-T06** | **DONE (2026-10-10)** | **`connector.fetch` spans on every external call (A11, A14)** |

## M2-T05: point-in-time XBRL

- **Real payload studied.** LULU `companyfacts` was fetched once (2.97 MB, 20,022 facts). The
  field names (`accn end filed form fp frame fy start val`) were verified against it. LULU
  alone has 350 restated groups, where the same period carries a different value in a later
  filing.
- **The rule.** A fact becomes available at its accession's EDGAR acceptance time. As of a
  cutoff, the latest accepted fact for that concept, unit and period wins. An unknown
  acceptance time means not eligible, whatever the `filed` date says. The SEC aggregate
  endpoint is never called, and a test checks the module source for it.
- **Real restatement in the fixture.** LULU's accrued liabilities at 2021-01-31 read 211,911,000
  USD in three 10-Qs (accepted Jun–Dec 2021). The 10-K accepted 2022-03-30 restated it to
  226,867,000. A cutoff of 2022-01-01 returns the original; 2022-04-01 returns the restatement.
- **Citable.** Each selected fact becomes its own document version, provider-verified at its
  acceptance time. Its span is the fact's exact JSON object in the preserved payload. Against
  the full real payload, 300 of 300 random facts were located exactly.
- **End to end with M1-T05.** Two XBRL facts feed a `difference` derivation of +14,956,000 USD,
  and the validator recomputes it with zero failed checks.

## M2-T06: connector spans

Each Alpha Vantage, EDGAR and XBRL call is one `connector.fetch` span. It records source,
operation, host, outcome (`ok`, `NO_DATA`, `SOURCE_FAILED`, `NOT_AUTHORIZED`), byte size and
SHA-256. It never records the body, query string, full URL or key; a test proves this with a key
that redaction does not know. The spans appeared in `spans.jsonl` and in Phoenix.

**Leak fixed along the way:** an error span's status message used to carry the exception text.
For connectors that text can include a response body or a URL with `apikey=`. Spans now record
only the exception class and error code.

## Numbers

| Measure | Before | After |
|---|---:|---:|
| `tests/evidence` | 139 | 168 |
| Default suite | 370 | 399 |
| Live SEC requests | 0 | 2 (companyfacts and submissions, LULU) |

## Deviations (recorded in the journals)

- **`accounting_basis` for XBRL facts is the taxonomy** (`us-gaap`), not form plus fiscal
  period. The pack's choice would have failed every cross-period derivation.
- **Fact-level documents.** Today's companyfacts download is a first capture, so as a single
  document it would be ineligible for every historical cutoff.
- **SEC User-Agent.** It carried the owner's contact email, as SEC fair access requires. The
  email is in no repository file.

## Open items

- **Owner checkpoint (G2):** live ingestion of LULU, TSCO and CALX, and hand inspection of their
  key quotations. M4-T04 (the real thesis review) is blocked until the case mapping is
  confirmed.
- **For the owner to confirm:** EDGAR `acceptanceDateTime` values carry a `Z` and are treated as
  UTC. If EDGAR actually means US Eastern, every recorded availability time is 4–5 hours too late.
  That errs on the conservative side, but should be confirmed.
- **`http.response.status_code` is not on connector spans.** The `Transport` callable returns
  only a body.
