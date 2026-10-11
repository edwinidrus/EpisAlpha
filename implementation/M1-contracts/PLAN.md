# M1 plan: canonical contracts and epistemic invariants

**Goal:** remove ambiguity before database and agent code diverge. Close the derivation gap so
that every derived number is recomputed rather than trusted.

**Plan source:** plan §7 (M1-T01..T04), §3.2–3.5; amendment A8.

## Tasks

| Task | Title | Status | Depends on | Pack |
|---|---|---|---|---|
| M1-T01 | Knowledge contracts | DONE | G0 | — |
| M1-T02 | Research contracts, lifecycle, errors | DONE | M1-T01 | — |
| M1-T03 | Temporal eligibility policy | DONE | M1-T02 | — |
| M1-T04 | Structural evidence and graph validator | DONE | M1-T03 | — |
| M1-T05 | Derivation registry and recomputation (A8) | DONE | G1 | [pack](tasks/M1-T05-derivations.md) |

## Scope

- **In:** `research/derivations.py` and `check_derivations` in `research/validation.py`.
- **Out:**
  - The XBRL facts that feed derivations (M2-T05).
  - The `compute_derivation` tool (M3-T01).
  - The UI derivation chain (M5-T02).

## Known gap, not scheduled

`progress.md` finding 5: the validator does not yet enforce "an `unverified` source cannot be
the sole support" (plan §3.4, A2). Social sources ship disabled, so this is not blocking.
**Before any `unverified` source is enabled**, add a task card here (`M1-T06`) to enforce it.
Do not enable `reddit` or `stocktwits` until it exists.

## Existing interfaces M1-T05 builds on (seen 2026-10-10)

| Name | Location |
|---|---|
| `NumericFact` (metric, value: `DecimalString`, unit, period_start, period_end, accounting_basis, source_context) | `src/episalpha/contracts/knowledge.py:265` |
| `Derivation` (method, method_version, input_claim_ids) | `knowledge.py:283` |
| `Claim.derivation`, `Claim.numeric_fact` | `knowledge.py:291` |
| `RecordSet`, `_ok`, `_fail`, `check_claim_references` | `src/episalpha/research/validation.py:42,76,80,121` |
| `validate()` (assembles checks; any failure leads to `REJECTED` / `INVALID_OUTPUT`) | `validation.py:257` |
