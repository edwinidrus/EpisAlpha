# M7 plan: demo acceptance, recovery and handoff

**Goal:** a repeatable demonstration with honest failure behaviour, and a clear implementation
handoff.

**Plan source:** plan §13 (M7-T01..T03), §14 acceptance matrix, §15 definition of done.

## Tasks

| Task | Title | Status | Depends on | Pack |
|---|---|---|---|---|
| M7-T01 | Cross-boundary acceptance suite | TODO | G6 | [pack](tasks/M7-T01-acceptance-suite.md) |
| M7-T02 | Demo packaging and smoke command | TODO | M7-T01 | [pack](tasks/M7-T02-smoke.md) |
| M7-T03 | Final owner walkthrough | TODO | M7-T02 | [pack](tasks/M7-T03-walkthrough.md) |

## Acceptance matrix ownership (plan §14), for M7-T01 coverage

| ID | Scenario | Owner phases |
|---|---|---|
| A01 | Valid supported case | M4 |
| A02 | Conflicting sources | M4, M5 |
| A03 | Essential evidence missing | M4 |
| A04 | Source unavailable gives `SOURCE_FAILED` | M2, M4 |
| A05 | Future source added later | M2, M4 |
| A06 | Restatement or correction | M1, M2 |
| A07 | Fabricated citation or quote | M1, M4 |
| A08 | Injection in document | M3, M7 |
| A09 | Worker attempts forbidden access | M3 |
| A10 | Budget, timeout or cancel | M3, M4 |
| A11 | Browser refresh | M5 |
| A12 | Saved replay with network blocked | M4 |
| A13 | Fresh run on same snapshot | M4 |
| A14 | Invalid graph relation | M1, M5 |
| A15 | Obsidian export repeated | M5 |
| A16 | Candidate edits forbidden field | M6 |
| A17 | Empty or failed candidate answer | M6 |
| A18 | Candidate does not improve | M6 |
| A19 | Crash and recovery | M4, M7 |
| A20 | Source or object artifact altered | M2, M4 |
| A21 | Copied articles cite same source | M2, M5 |
| A22 | Unknown usage or pricing | M3, M5 |
| A23 | Historical reconstruction label | M1, M5 |
| A24 | Evaluator input changed | M6 |
| A25 (A8) | Derived number wrong | M1, M4 |
| A26 (A11) | Secret in any log | M0, M2, M3 |

A25 and A26 extend the matrix for amendments A8 and A11. Both are additive.
