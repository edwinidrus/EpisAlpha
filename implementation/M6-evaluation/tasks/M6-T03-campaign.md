# M6-T03 — Offline campaign runner

| Field | Value |
|---|---|
| Status | TODO |
| Depends on | M6-T02 |
| Phase constitution | [../CONSTITUTION.md](../CONSTITUTION.md) (inherits [global](../../CONSTITUTION.md)) |
| Plan source | plan §12.2, §12.3, M6-T03 card |
| Journal | `tasks/M6-T03-campaign.journal.md` |
| Live calls | Yes, for the final live campaign: about 100–200 requests. **An owner decision on free-tier capacity is required.** |

## 0. Context to load

Load these and nothing else:
- `implementation/CONSTITUTION.md`
- `implementation/M6-evaluation/CONSTITUTION.md`, all articles
- [../PLAN.md](../PLAN.md), the decision rule and the owner decisions
- `src/episalpha/evolution/candidates.py` (M6-T02)
- `src/episalpha/evaluation/cases.py` and `scoring.py` (M6-T01)
- `src/episalpha/research/runner.py`, where the bounded optional retrieval step is added
- `src/episalpha/cli.py`

**The commands:**

```bash
uv run episalpha experiment compare --campaign demo-v1 --runtime fake
uv run episalpha experiment compare --campaign demo-v1 --runtime hermes
```

## 1. Plan

- **Goal:** one campaign. It summarizes development failures, takes one candidate proposal,
  validates it, and runs baseline and challenger in pairs on identical snapshots and fixed
  budgets. It compares on validation, runs the frozen config on the final-check cases only after
  validation passes, and records everything in the ledger.
- **Files:**
  - `src/episalpha/evolution/campaign.py`
  - `src/episalpha/cli.py`
  - `src/episalpha/research/runner.py`. When `contradiction_search` is true, this adds **one
    bounded extra retrieval step** over the same frozen corpus. It never removes evidence
    requirements and never expands access.
  - Focused test: `tests/evolution/test_campaign.py` (fake runtime)
- **Build:**
  - The campaign manifest freezes:
    - the decision rule (plan §12.3);
    - the case partitions;
    - the evaluator and label hashes;
    - the budgets;
    - the runtime mode;
    - the provider/model.

    It is written **before** any validation result exists.
  - The execution ID is a hash over (runtime mode, provider/model, snapshot, harness/config,
    evaluator hash, label hash, attempt).
  - Isolation:
    - The candidate author sees development failures plus the patch schema only.
    - The worker sees only its case input.
    - Only the evaluator loads labels.
  - Every trial is persisted, including interrupted and failed ones.
  - **There is no automatic baseline replacement.**
  - Variability: two fresh runs per variant and case if the budget allows. Otherwise record the
    single-run limitation. Seeds are recorded when supported; they are not a determinism
    guarantee.
  - The runner checks the requests remaining against the free-tier cap. When it is exhausted,
    the campaign **pauses** and records a resumable state. It never truncates silently.
- **Do not:**
  - Let fake results satisfy live.
  - Re-run a case to "get a better result".
  - Reuse final-check cases for tuning after exposure.

## 2. Verify (before building)

- [ ] The owner decision on free-tier capacity (credits or multi-day) is recorded in M6
      `PROGRESS.md`. Without it, the live campaign is **BLOCKED**; the fake path can still
      complete.
- [ ] Labels are human-validated (the M6-T01 checkpoint).
- [ ] Baseline: the four checks and `diagnose.py` are green.
- [ ] **Red first.** Write `test_campaign.py` with the fake runtime. Cover:
  - The manifest is frozen before the validation scores exist (ordering asserted).
  - Fake and real execution IDs are distinct for `demo-v1`.
  - The candidate author's inputs contain no labels.
  - An interrupted trial is recorded.
  - The baseline is retained when any rule fails.
  - The final check runs only after validation passes.
  - Budget exhaustion gives a paused, resumable campaign.

## 3. Build

1. Write the campaign manifest and execution identity.
2. Write paired execution and the ledger.
3. Write the decision-rule evaluation, gate by gate.
4. Write the CLI command.
5. Write the bounded `contradiction_search` step in the runner.

## 4. Test

```bash
uv run pytest -q tests/evolution/test_campaign.py
uv run episalpha experiment compare --campaign demo-v1 --runtime fake
uv run ruff check . && uv run ruff format --check . && uv run mypy src/episalpha && uv run pytest -q -m "not live"
```

Acceptance:
- [ ] The candidate author sees no hidden inputs or labels.
- [ ] The research worker sees only its current case input.
- [ ] Only the evaluator loads labels.
- [ ] Identities include runtime mode, provider/model, snapshot, harness/config,
      evaluator/label hashes and attempt.
- [ ] Fake and real campaigns get distinct IDs.
- [ ] Interrupted and failed trials remain recorded.
- [ ] There is no automatic baseline replacement.
- [ ] One explicit live campaign is completed, or it is BLOCKED with the reason and schedule.

## 5. Diagnose

- [ ] `diagnose.py`: no regression.
- [ ] The `eval.trial` and `eval.decision` events reconstruct the campaign. Paste a `jq`
      summary into the journal.
- [ ] Record the free-tier requests spent per day.

## 6. Stop and hand off

- **BLOCKED if:** there is no capacity decision, or the labels are not validated.
- **Record:** M6 `PROGRESS.md`, `STATUS.md`, and the journal.
- **Next:** M6-T04.
