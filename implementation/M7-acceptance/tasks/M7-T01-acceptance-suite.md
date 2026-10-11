# M7-T01 — Cross-boundary acceptance suite

| Field | Value |
|---|---|
| Status | TODO |
| Depends on | G6 |
| Phase constitution | [../CONSTITUTION.md](../CONSTITUTION.md) (inherits [global](../../CONSTITUTION.md)) |
| Plan source | plan §13 M7-T01 card, §14 matrix |
| Journal | `tasks/M7-T01-acceptance-suite.journal.md` |

## 0. Context to load

Load these and nothing else:
- `implementation/CONSTITUTION.md`
- `implementation/M7-acceptance/CONSTITUTION.md`
- [../PLAN.md](../PLAN.md), the matrix ownership table (A01–A29 and A32; A30–A31 belong to G8)
- the phase journals, to find existing tests per row (`grep -rn "A0\|A1\|A2" implementation/*/tasks/*.journal.md`)
- `implementation/DIAGNOSTICS.md`, which shows the test inventory per directory

## 1. Plan

- **Goal:** one end-to-end suite proves every acceptance row across the boundaries of UI, tools,
  storage, replay, export and evaluation. It uses the fake provider or runtime wherever external
  model behaviour is not the thing being verified.
- **Files:**
  - `tests/integration/test_demo_acceptance.py`
  - Focused fixtures
  - The responsible production module, **only** if a failure needs a correction, recorded first
- **Build:**
  - One test per row, named `test_A01_...` through `test_A29_...`, plus `test_A32_...`.
  - Where a lower-level test already proves a row, the acceptance test drives it across the
    boundary instead of duplicating it. For example, A12 drives replay through the CLI with the
    network blocked.
  - Rows that are manual-only (parts of A11 and A15) are marked `pytest.mark.skip(reason="manual: see GATE")`
    **and** are listed in `GATE.md` as manual checks. They are never silently skipped.
  - A26: run a full fake run with a sentinel secret in the environment, then grep every log and
    artifact file for it.
- **Do not:**
  - Mark a fixture as live.
  - Relax an expectation to get green.

## 2. Verify (before building)

- [ ] G6 has passed. The four checks and `diagnose.py` are green.
- [ ] A row-to-test map is drafted in the journal, before any code, from the existing tests.

## 3. Build

1. Write the shared end-to-end fixtures: temporary settings, seeded corpus, and fake runtime
   scripts.
2. Write the row tests in matrix order. Each failure goes to the journal first (row, observed
   behaviour, responsible module), then gets a narrow fix.

## 4. Test

```bash
uv run pytest -q tests/integration/test_demo_acceptance.py
uv run ruff check . && uv run ruff format --check . && uv run mypy src/episalpha && uv run pytest -q -m "not live"
```

Acceptance:
- [ ] All deterministic invariants pass.
- [ ] No fixture is mislabeled live.
- [ ] Snapshot and reference boundaries remain intact across UI, tools, storage, replay, export
      and evaluation.
- [ ] Every row in A01–A29 and A32 is automated or listed as a manual check.

## 5. Diagnose

- [ ] `diagnose.py`: no regression. The traceability section shows no orphan tests.
- [ ] The journal holds the row-to-test map in its final state.

## 6. Stop and hand off

- **Record:** M7 `PROGRESS.md`, `STATUS.md`, and the journal.
- **Next:** M7-T02.
