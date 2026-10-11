# EpisAlpha implementation workspace

This folder is the **operational layer** of the v0.1 build. The governing plan
(`../EpisAlpha_MVP_Milestone_Implementation_Plan.md`) remains the source of frozen contracts
(§§1–4) and the acceptance matrix (§14). This folder breaks the plan into phase folders and
self-contained task packs, so a coding model loads only the context one task needs.

## Layout

```text
implementation/
├── README.md            # this file: the session protocol
├── CONSTITUTION.md      # global articles; binding on every phase and task
├── STATUS.md            # one row per task across all phases; the "next task" pointer
├── DIAGNOSTICS.md       # latest health snapshot (written by scripts/diagnose.py, from M0-T05)
├── logs/diagnose.jsonl  # append-only diagnose history, one JSON line per run (from M0-T05)
├── templates/TASK.md    # skeleton for new task packs
└── M<n>-<name>/
    ├── CONSTITUTION.md  # phase articles; inherits ../CONSTITUTION.md
    ├── PLAN.md          # goal, scope, task order, dependencies, open questions
    ├── PROGRESS.md      # Task | Status | Changes | Verification | Blocker | Next
    ├── GATE.md          # gate commands, criteria checklist, results log
    └── tasks/
        ├── M<n>-T<nn>-<slug>.md          # task pack (pending tasks only)
        └── M<n>-T<nn>-<slug>.journal.md  # append-only attempt log, created at first attempt
```

Phases: [M0-foundation](M0-foundation/PLAN.md) · [M1-contracts](M1-contracts/PLAN.md) ·
[M2-evidence](M2-evidence/PLAN.md) · [M3-runtime](M3-runtime/PLAN.md) ·
[M4-research-cli](M4-research-cli/PLAN.md) · [M5-browser-obsidian](M5-browser-obsidian/PLAN.md) ·
[M6-evaluation](M6-evaluation/PLAN.md) · [M7-acceptance](M7-acceptance/PLAN.md) ·
[M8-learning](M8-learning/PLAN.md) (post-v0.1, A13)

## Session protocol (one task per session)

1. **Pick.** Open [STATUS.md](STATUS.md). Take the first `TODO` row whose dependencies are all
   `DONE`. Never take two tasks at once.
2. **Load exactly this context, nothing more:**
   - [CONSTITUTION.md](CONSTITUTION.md)
   - the phase `CONSTITUTION.md`
   - the task pack
   - the files the pack names under "Context to load"

   Open the big plan only at the line references the pack gives.
3. **Work the pack's five steps in order.** Do not skip a step.

   | Step | What it means |
   |---|---|
   | **Plan** | Restate the goal, scope and files in a few lines. If the pack is wrong or stale, stop and report it. |
   | **Verify** | Before building: every upstream interface the pack names exists with the stated signature; the four checks are green; the focused tests are written first and fail for the expected reason. |
   | **Build** | Smallest change that satisfies acceptance. Stay inside the pack's file list. |
   | **Test** | Focused test, then the four standard checks. Tick every acceptance item. |
   | **Diagnose** | Run `uv run python scripts/diagnose.py` (once M0-T05 exists). Check there is no regression against the previous `logs/diagnose.jsonl` line. Check the pack's expected spans, in `spans.jsonl` or the local Phoenix (once M0-T06/T07 exist). Write the journal entry. |

4. **Record.**
   - Phase `PROGRESS.md` row: exact commands and *real* output.
   - [STATUS.md](STATUS.md) row status.
   - The journal: every attempt, including failed ones.
5. **Stop.** Report the next task. Commits are an owner action.

### The four standard checks

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src/episalpha
uv run pytest -q -m "not live"
```

### Status values

`TODO` · `IN_PROGRESS` · `DONE` (acceptance passed, real output recorded) · `BLOCKED` (reason
and owner action in the Blocker column) · `DONE_OFFLINE` (offline acceptance passed, the live
part is still open).

### BLOCKED rules

Stop and report `BLOCKED` when any of these happens:
- an upstream interface is unverified or differs from the pack;
- a credential for a required live check is missing;
- a contract conflicts;
- the task needs an unapproved architectural change;
- two bounded attempts at the same issue have failed. The journal is the evidence for this.

A blocked live check stays blocked. Offline success is reported separately.

## Journal entry format

Append one block per attempt to `tasks/<task>.journal.md`. Never edit earlier blocks.

```markdown
## Attempt N — YYYY-MM-DD HH:MM UTC — <model id that did the work>
- Hypothesis: what I expected this change to achieve
- Did: files touched, in one line each
- Ran: `exact command` -> real result (shortest decisive line)
- Outcome: PASS | FAIL | BLOCKED
- Root cause (if FAIL): what was actually wrong, with evidence
- Decision: what I chose next and why
- Diagnose: diagnose.py summary line; expected spans seen yes/no; trace ID if any
```

The journal makes a delivery explainable as a white box: anyone can see why each line of code
looks the way it does, which attempts failed, and what evidence closed the task.
