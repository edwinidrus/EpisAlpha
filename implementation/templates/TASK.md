# M<n>-T<nn> — <title>

<!-- Copy into implementation/M<n>-<name>/tasks/. The relative links resolve from there. -->

| Field | Value |
|---|---|
| Status | TODO |
| Depends on | <task IDs / gate> |
| Phase constitution | [../CONSTITUTION.md](../CONSTITUTION.md) (inherits [global](../../CONSTITUTION.md)) |
| Plan source | `EpisAlpha_MVP_Milestone_Implementation_Plan.md` §<section>, amendment <A#> |
| Journal | `tasks/M<n>-T<nn>-<slug>.journal.md` (create on first attempt) |

## 0. Context to load

Load these and nothing else:
- `implementation/CONSTITUTION.md`
- `implementation/M<n>-<name>/CONSTITUTION.md`
- this pack
- <source files, read-only unless listed under Files>
- <existing tests that show the house style>

Contract excerpts the task depends on, copied here so the plan need not be opened:

> <excerpt> (plan §x.y)

## 1. Plan

- **Goal:** <one sentence, observable>
- **In scope:** <bullets>
- **Out of scope:** <bullets; later tasks own these>
- **Files:** <1–3 implementation files> + `<one focused test file>`
- **Consumes:** <existing functions/classes with path:line>
- **Produces:** <new public names and signatures>
- **Do not:** <specific traps>

## 2. Verify (before building)

- [ ] Each consumed interface exists with the stated signature (`grep -n` and paste the result
      into the journal).
- [ ] The four standard checks are green before any change. Record the counts.
- [ ] The focused tests are written first, run, and fail for the expected reason.
- [ ] <task-specific preconditions: credentials present, owner approval, upstream pin>

On any mismatch, record `BLOCKED` with evidence and stop.

## 3. Build

1. <ordered, bounded steps>

## 4. Test

```bash
uv run pytest -q <focused test>
uv run ruff check . && uv run ruff format --check . && uv run mypy src/episalpha && uv run pytest -q -m "not live"
```

Acceptance (tick each, with evidence):
- [ ] <observable criterion>

## 5. Diagnose

- [ ] `uv run python scripts/diagnose.py` passes, with no regression against the previous
      `implementation/logs/diagnose.jsonl` line.
- [ ] The expected spans appear (from M0-T06 onward): span names and kinds in
      `<data_root>/logs/spans.jsonl`, and in the local Phoenix if it is running (M0-T07).
      <span names>.
- [ ] A journal entry is written, with every attempt recorded.

## 6. Stop and hand off

- **BLOCKED if:** <task-specific triggers>
- **Record:** a phase `PROGRESS.md` row, the `STATUS.md` row, and the journal.
- **Next:** <task ID>
