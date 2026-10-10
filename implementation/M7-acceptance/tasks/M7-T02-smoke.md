# M7-T02 — Demo packaging and smoke command

| Field | Value |
|---|---|
| Status | TODO |
| Depends on | M7-T01 |
| Phase constitution | [../CONSTITUTION.md](../CONSTITUTION.md) (inherits [global](../../CONSTITUTION.md)) |
| Plan source | plan §13 M7-T02 card |
| Journal | `tasks/M7-T02-smoke.journal.md` |

## 0. Context to load

Load these and nothing else:
- `implementation/CONSTITUTION.md`
- `implementation/M7-acceptance/CONSTITUTION.md`, articles 4 and 5
- `README.md`
- `src/episalpha/cli.py`, the full command list
- `scripts/diagnose.py`, for the house style of a stdlib script

## 1. Plan

- **Goal:** one offline command proves the whole demo works from a clean checkout, without
  touching user state.
- **Files:**
  - `scripts/demo_smoke.py`
  - `README.md`
  - `docs/implementation/demo_acceptance.md`
  - Focused test: `tests/integration/test_smoke_script.py`
- **Build, `demo_smoke.py`:**
  1. Create temporary state (`tempfile.mkdtemp`) and a temporary settings file.
  2. Seed the fixtures.
  3. Run the three cases with `--runtime fake`.
  4. Replay each run with the network blocked.
  5. Export the vault.
  6. Run `experiment compare --runtime fake`.
  7. Back up and restore DB, objects and runs together, and verify the hashes.
  8. Print the output locations.

  It exits non-zero on any failed assertion. It uses the CLI through `subprocess`, the way a
  user would.
- **`README.md`:** clean-checkout steps, offline and live sections, the free-tier note, and
  where the logs and diagnostics live.
- **Do not:**
  - Read the real `.episalpha/`.
  - Require credentials.

## 2. Verify (before building)

- [ ] M7-T01 is green. The four checks and `diagnose.py` are green.
- [ ] **Red first.** Write `test_smoke_script.py`. It runs the script and asserts exit 0 and the
      printed locations, then injects a failure (for example, tamper with an artifact) and
      asserts a non-zero exit.

## 3. Build

1. Write the script, step by step, with an assertion after each step.
2. Write the backup and restore helper, inside the script.
3. Update the README and `demo_acceptance.md`.
4. Do a clean-checkout rehearsal: `git clone` into a temporary directory, then follow the README
   literally. Record the transcript in the journal.

## 4. Test

```bash
uv run python scripts/demo_smoke.py
uv run pytest -q tests/integration/test_smoke_script.py
uv run ruff check . && uv run ruff format --check . && uv run mypy src/episalpha && uv run pytest -q -m "not live"
```

Acceptance:
- [ ] A fresh environment follows the README successfully.
- [ ] The script exits non-zero on any failed assertion.
- [ ] Recorded replay works without provider or network.
- [ ] The DB, object and run backup restores together, with hashes checked.

## 5. Diagnose

- [ ] `diagnose.py`: no regression.
- [ ] The smoke runtime is measured and recorded, against the plan's performance target: the
      saved corpus opens in 5 s or less after warm-up.

## 6. Stop and hand off

- **Record:** M7 `PROGRESS.md`, `STATUS.md`, and the journal.
- **Next:** M7-T03.
