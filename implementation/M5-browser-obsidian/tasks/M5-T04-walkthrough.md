# M5-T04 — Browser walkthrough and usability correction

| Field | Value |
|---|---|
| Status | TODO |
| Depends on | M5-T03 |
| Phase constitution | [../CONSTITUTION.md](../CONSTITUTION.md) (inherits [global](../../CONSTITUTION.md)) |
| Plan source | plan §11 M5-T04 card |
| Journal | `tasks/M5-T04-walkthrough.journal.md` |

## 0. Context to load

Load these and nothing else:
- `implementation/CONSTITUTION.md`
- `implementation/M5-browser-obsidian/CONSTITUTION.md`
- `apps/streamlit_app.py`
- the M5-T01..T03 journals (the known rough edges)

## 1. Plan

- **Goal:** a six-minute walkthrough works for the owner, end to end, and the usability fixes it
  reveals are made narrowly.
- **Files:**
  - `apps/streamlit_app.py`
  - `docs/implementation/demo_script.md`
  - Focused test: `tests/ui/test_workbench.py`, for core navigation
- **Walkthrough script:**
  1. Select a case.
  2. View the thesis.
  3. Inspect a quote.
  4. Inspect a contradiction.
  5. Browse the graph and export.
  6. Show saved replay.

  The experiment segment is reserved for M6.
- **Out of scope:** new features. Any fix must trace to a walkthrough finding recorded first in
  the journal.

## 2. Verify (before building)

- [ ] M5-T01..T03 are DONE. The four checks and `diagnose.py` are green.
- [ ] **Red first.** Write `test_workbench.py`, which navigates assertion to claim to passage in
      3 interactions or fewer, using `AppTest`, and checks that missing information is visible on
      the Research tab.

## 3. Build

1. Write `demo_script.md`: steps, expected screen, timing per step.
2. The owner, or the model acting as the user, performs the walkthrough. Record each friction
   point in the journal first, then apply the minimal fixes.
3. Record the manual Obsidian check: the vault opens and the local links work.

## 4. Test

```bash
uv run pytest -q tests/ui tests/knowledge
uv run ruff check . && uv run ruff format --check . && uv run mypy src/episalpha && uv run pytest -q -m "not live"
```

Acceptance:
- [ ] The owner can navigate from a thesis assertion to the original passage in 3 deliberate
      clicks or fewer.
- [ ] Missing information is visible without opening logs.
- [ ] Obsidian opens the exported vault with working local links. This is a manual check,
      recorded with the date and Obsidian version.

## 5. Diagnose

- [ ] `diagnose.py`: no regression.
- [ ] Run G5 and append the result to `../GATE.md`, with the manual checks recorded separately
      from the automated ones.

## 6. Stop and hand off

- **BLOCKED if:** the owner is not available for the manual checks. Report the automated part
  as DONE_OFFLINE.
- **Record:** M5 `PROGRESS.md`, `STATUS.md`, and the journal.
- **Next:** M6-T01.
