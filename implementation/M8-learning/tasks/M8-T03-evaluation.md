# M8-T03 — Offline paired skill evaluation

| Field | Value |
|---|---|
| Status | TODO |
| Depends on | M8-T02 |
| Phase constitution | [../CONSTITUTION.md](../CONSTITUTION.md) (inherits [global](../../CONSTITUTION.md), section VIII) |
| Plan source | amendment A13; M6 decision rule (plan §12.3) |
| Journal | `tasks/M8-T03-evaluation.journal.md` |
| Live calls | Yes. About 96 requests per candidate. The owner's capacity decision is required (see PLAN). |

## 0. Context to load

Load these and nothing else:
- `implementation/CONSTITUTION.md`, section VIII
- `implementation/M8-learning/CONSTITUTION.md`, articles 5 and 10
- `implementation/M6-evaluation/CONSTITUTION.md`, articles 2, 5–10
- `src/episalpha/evolution/campaign.py` (M6-T03): paired runs, execution identity, pause and
  resume
- `src/episalpha/evaluation/scoring.py` and `cases.py` (M6-T01)
- `src/episalpha/learning/skills.py` and `screening.py`

## 1. Plan

- **Goal:** decide, on fixed evidence, whether adding one candidate skill makes research better
  without making anything worse.
- **Files:**
  - `src/episalpha/learning/evaluation.py` (new)
  - Focused test: `tests/learning/test_skill_evaluation.py` (fake runtime)
- **Build:**
  - `evaluate(candidate) -> SkillEvalReport`. It reuses the M6 campaign runner with:
    - variant A, the current promoted set;
    - variant B, that set plus the candidate.

    Both use identical snapshots, budgets, cases (development plus validation) and evaluator
    and label hashes.
  - The execution identity includes both skill-set hashes.
  - **Gates, frozen in `SkillEvalManifest` before any run:**
    1. Zero temporal, reference and boundary violations in both variants.
    2. No regression on any M6 metric: citation correctness, numeric correctness,
       supported-claim precision, required-fact recall, contradiction recall, correct
       abstention, completion.
    3. A gain on the candidate's **targeted metric**, chosen from its `when_to_use` category at
       screening time, for example numeric correctness for a derivation skill.
    4. Requests and latency at most 1.25× variant A.
  - The result sets the ledger state, `evaluating` → `rejected`, or stays `evaluating` with
    `eval_passed`. Promotion is M8-T04, by a human.
  - Free-tier scheduling: check the remaining daily cap, pause and resume, never truncate cases.
- **Do not:**
  - Re-run until a pass.
  - Reuse M6 final-check cases. They stay sealed.
  - Evaluate more than one candidate per paired campaign. That would make attribution
    impossible.

## 2. Verify (before building)

- [ ] The M6 campaign runner accepts a skill-set variant. If it does not, the smallest change
      lives in `evolution/campaign.py`, inside this task's budget, or the task is split.
- [ ] Labels are sealed and their hashes recorded (M6-T01).
- [ ] The owner's capacity decision is recorded. Without it, the live part is BLOCKED; the fake
      path can still complete.
- [ ] **Red first.** Write `test_skill_evaluation.py`. Cover:
  - The manifest is frozen before scores exist.
  - Any regression rejects.
  - No targeted gain rejects.
  - A pass leaves the skill `evaluating` with `eval_passed` (never `promoted`).
  - Pause and resume at the cap.
  - The execution IDs differ between variants and between fake and live.

## 3. Build

1. Write the manifest and the identity.
2. Write paired execution through the M6 runner.
3. Write the gate evaluation and the ledger transition.
4. Write the report: per-case pairs, numerators and denominators, gates, cost, latency.

## 4. Test

```bash
uv run pytest -q tests/learning/test_skill_evaluation.py
uv run ruff check . && uv run ruff format --check . && uv run mypy src/episalpha && uv run pytest -q -m "not live"
```

Acceptance:
- [ ] The gates are applied as frozen.
- [ ] Rejection is a complete result.
- [ ] A pass never promotes.
- [ ] One live evaluation of one real candidate is recorded, or BLOCKED with the schedule.

## 5. Diagnose

- [ ] `diagnose.py`: no regression.
- [ ] A `skill.evaluated` event per candidate, with per-metric numerators and denominators.
- [ ] Journal: the requests spent per day against the cap.

## 6. Stop and hand off

- **BLOCKED if:** there is no capacity decision, or the M6 runner cannot take a skill-set
  variant within the file budget.
- **Record:** M8 `PROGRESS.md`, `STATUS.md`, and the journal.
- **Next:** M8-T04.
