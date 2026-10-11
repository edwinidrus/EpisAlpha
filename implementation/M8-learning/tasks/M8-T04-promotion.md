# M8-T04 — Promotion, revocation and temporal availability

| Field | Value |
|---|---|
| Status | TODO |
| Depends on | M8-T03 |
| Phase constitution | [../CONSTITUTION.md](../CONSTITUTION.md) (inherits [global](../../CONSTITUTION.md), section VIII) |
| Plan source | amendment A13; plan §3.5 rule 9; acceptance row A31 |
| Journal | `tasks/M8-T04-promotion.journal.md` |

## 0. Context to load

Load these and nothing else:
- `implementation/CONSTITUTION.md`, sections II and VIII
- `implementation/M8-learning/CONSTITUTION.md`, articles 6–9 and 11
- `src/episalpha/learning/skills.py`, `screening.py` and `evaluation.py`
- `src/episalpha/cli.py`
- `src/episalpha/research/runner.py`, where the run selects its skill set

**The commands:**

```bash
uv run episalpha skills list [--status evaluating]
uv run episalpha skills show SKILL_ID          # diff, provenance, screen report, eval report
uv run episalpha skills approve SKILL_ID --by "<name>"
uv run episalpha skills reject SKILL_ID --reason "..."
uv run episalpha skills revoke SKILL_ID --reason "..."
uv run episalpha skills revoke --source RUN_ID|DOCUMENT_ID --reason "..."   # cascade
```

## 1. Plan

- **Goal:** a human decides every promotion with full evidence. Revocation cascades through
  provenance. Each run uses exactly the skill set that is valid for its time.
- **Files:**
  - `src/episalpha/learning/promotion.py` (new)
  - `src/episalpha/cli.py`
  - `src/episalpha/research/runner.py` (skill-set selection)
  - Focused test: `tests/learning/test_promotion.py`
- **Build:**
  - `approve`:
    - It requires status `evaluating`, with `eval_passed` and an evaluation report whose hashes
      still match. Otherwise it fails.
    - It writes `<id>@v<n>` to the library, then `promoted` with `promoted_at` and
      `approved_by` to the ledger.
    - The CLI shows the `show` output and asks for typed confirmation. A `--yes` flag exists
      for scripting but still records `approved_by`.
  - `revoke`:
    - Marks a skill `revoked`.
    - `--source` revokes every skill whose provenance contains that run or document, together
      with skills derived from those.
    - It is idempotent, and every revocation is recorded.
  - Runner selection:
    - Forward runs use `skill_set(as_of=None)`.
    - Historical-reconstruction runs use `skill_set(as_of=research_cutoff)`.
    - The selected set is mounted read-only (M3-T04), and its hash is recorded on the run.
- **Do not:**
  - Promote from any path other than `approve`, including tests' production code paths.
  - Promote without `approved_by`.
  - Hard-delete anything.

## 2. Verify (before building)

- [ ] M8-T01..T03 are DONE. The runner already records the skill-set hash (M4-T01).
- [ ] Baseline: the four checks and `diagnose.py` are green.
- [ ] **Red first.** Write `test_promotion.py`. Cover:
  - Approve fails without `eval_passed`, and when the evaluation hash has changed.
  - Approve records the actor and time, and creates an immutable library file.
  - Reject records the reason.
  - Revoke removes the skill from the next run's set, and the set hash changes (A31).
  - Revoking by source cascades.
  - A historical run with an earlier cutoff excludes a later-promoted skill.
  - No code path except `approve` produces `promoted`. Check this by grepping transitions in
    the source.

## 3. Build

1. Write the promotion and revocation functions over the ledger and library.
2. Write the CLI sub-app.
3. Write the runner skill-set selection and mount.

## 4. Test

```bash
uv run pytest -q tests/learning
uv run ruff check . && uv run ruff format --check . && uv run mypy src/episalpha && uv run pytest -q -m "not live"
```

Acceptance:
- [ ] Human approval is mandatory and recorded.
- [ ] Revocation cascades and changes the next run's skill-set hash.
- [ ] Temporal availability is enforced for historical runs.
- [ ] One real candidate's owner decision is recorded end to end.

## 5. Diagnose

- [ ] `diagnose.py`: no regression.
- [ ] `skill.promoted`, `skill.rejected` and `skill.revoked` events carry the actor and reason.
- [ ] Run G8 and append the result to `../GATE.md`.

## 6. Stop and hand off

- **Record:** M8 `PROGRESS.md`, `STATUS.md`, and the journal.
- **Next:** none in this plan. Further learning work needs a new owner-approved amendment.
