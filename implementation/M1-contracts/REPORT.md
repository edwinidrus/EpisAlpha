# M1 phase report: canonical contracts and epistemic invariants

**Gate G1: PASSED on 2026-10-10** (re-run after amendment A8). One owner item is open: review
the serialized examples below. Real output is in [PROGRESS.md](PROGRESS.md),
[GATE.md](GATE.md) and the journals.

## What M1 delivers

| Task | Status | What exists now |
|---|---|---|
| M1-T01 | DONE (2026-09-20) | Knowledge contracts: entities, instruments, documents, spans, claims, events, hypotheses, relations, assessments |
| M1-T02 | DONE (2026-09-20) | Research contracts, run lifecycle, frozen error codes |
| M1-T03 | DONE (2026-09-20) | Temporal eligibility policy (six clocks) |
| M1-T04 | DONE (2026-09-20) | Structural validator: references, relations, exact quotations, semantic status |
| **M1-T05** | **DONE (2026-10-10)** | **Derivation registry: every derived number is recomputed by the validator (A8)** |

## M1-T05 in one paragraph

Before this task the validator checked only that a derived claim's inputs existed. Now
`check_derivations` recomputes each derived value. It uses the named method and version from a
read-only registry of six pure-`Decimal` methods: `difference`, `pct_change`, `ratio`,
`margin`, `range_midpoint` and `guidance_revision`, all at version 1. The recomputed value is
rounded half-even to the digits the claim states, then compared. A claim fails when:
- the value does not match;
- the method or version is unknown, or the number of inputs is wrong;
- the inputs' units, accounting bases or periods do not fit the method;
- a divisor is zero (a failed check, never `0`);
- a number is missing, or the claimed unit differs from the method's output unit.

A missing input is still reported once, by the references check. The schema did not change,
and no float appears in the module (checked by an AST test).

## Numbers

| Measure | Value |
|---|---:|
| New focused tests | 29 |
| G1 command set | 212 passed |
| Default suite | 341 → 370 passed |
| Contract or existing-test changes | none (`git diff` empty) |

## For the owner's review: one derived claim, serialized

`pct_change@1` over Q3 revenue `400.00 EUR` and Q4 revenue `420.92 EUR` gives (420.92 −
400.00) / 400.00 = `0.0523`. The validator's result is
`claim.synthetic-claim.revenue-growth.derivation: passed`. A claimed `0.06` would be rejected:
"claims 0.06 but pct_change@1 recomputed 0.0523 ratio".

```json
{
  "claim_id": "synthetic-claim.revenue-growth",
  "statement": "Revenue grew 5.23% quarter over quarter.",
  "subject_ids": [
    "synthetic-issuer.eq"
  ],
  "attribution": "EpisAlpha derivation",
  "epistemic_status": "derived",
  "span_ids": [],
  "derivation": {
    "method": "pct_change",
    "method_version": "1",
    "input_claim_ids": [
      "synthetic-claim.revenue-q3",
      "synthetic-claim.revenue-q4"
    ]
  },
  "numeric_fact": {
    "metric": "revenue_growth_qoq",
    "value": "0.0523",
    "unit": "ratio",
    "period_start": "2025-10-01T00:00:00Z",
    "period_end": "2025-12-31T00:00:00Z",
    "accounting_basis": "IFRS consolidated",
    "source_context": "pct_change of Q3 and Q4 revenue"
  },
  "semantic_review_status": "unreviewed",
  "created_at": "2026-09-20T12:00:00Z",
  "run_id": null
}
```

The reported input claims look the same as the existing fixture `REPORTED_CLAIM` in
`tests/fixtures/synthetic_knowledge.py`: `epistemic_status: reported`, a cited span, and a
`numeric_fact` with value, unit, period, accounting basis and source context.

## Deviations

- **Red-first discipline slipped once.** The test file was written before the module but not
  run red before the module existed. The first run found three test-side bugs (identifiers
  shorter than the 3-character rule). Recorded in the journal.

## Open items

- **Owner:** review the serialized example above (G1's last criterion).
- **Rounding limit:** precision follows the claim's stated digits, so a coarse claim such as
  `0.05` for `0.0523` passes. This is marked in code as a known limit, with the upgrade path
  (a minimum-precision rule).
