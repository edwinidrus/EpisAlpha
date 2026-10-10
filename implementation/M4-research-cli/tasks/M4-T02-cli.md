# M4-T02 — CLI commands

| Field | Value |
|---|---|
| Status | TODO |
| Depends on | M4-T01 |
| Phase constitution | [../CONSTITUTION.md](../CONSTITUTION.md) (inherits [global](../../CONSTITUTION.md)) |
| Plan source | plan §10 M4-T02 card (exact interface) |
| Journal | `tasks/M4-T02-cli.journal.md` |

## 0. Context to load

Load these and nothing else:
- `implementation/CONSTITUTION.md`
- `implementation/M4-research-cli/CONSTITUTION.md`, articles 3 and 8
- `src/episalpha/cli.py` (the existing Typer app with `--version`)
- `src/episalpha/research/runner.py` (M4-T01)
- `src/episalpha/settings.py`, `load_settings`
- `src/episalpha/observability.py`, `configure_logging`
- `eval_cases/manifests/*.json` (the case definitions: `supported`, `conflicting`,
  `insufficient`)
- `tests/integration/test_package.py` (the CLI test style)

**The exact interface, which must not change:**

```bash
uv run episalpha demo seed
uv run episalpha research run --case supported --runtime fake
uv run episalpha research run --case conflicting --runtime hermes
uv run episalpha research status RUN_ID
uv run episalpha research execute RUN_ID  # Internal worker entry point
uv run episalpha research cancel RUN_ID
uv run episalpha replay RUN_ID
uv run episalpha research run --snapshot SNAPSHOT_ID --question "What changed and why might it matter?" --runtime hermes
```

> `--case` and `--snapshot` are mutually exclusive. A case includes question/cutoff. Snapshot
> reruns require `--question "..."`; the snapshot fixes cutoff and instrument scope, and v0.1
> rejects multi-instrument snapshots for a single thesis. Admission records runtime mode, so
> fake and real runs cannot collide. Internal worker entry point is not a second job-admission
> path. (plan M4-T02)

## 1. Plan

- **Goal:** the CLI is a thin shell over the runner's application services, with exact commands,
  distinct exit codes and safe output.
- **Files:**
  - `src/episalpha/cli.py`
  - CLI fixtures under `tests/fixtures/cli/`
  - Focused test: `tests/integration/test_cli_research.py` (Typer `CliRunner`, temporary data
    directories)
- **Exit codes** (frozen here; document them in `--help`):

  | Code | Meaning |
  |---|---|
  | 0 | Completed |
  | 2 | Invalid usage or request |
  | 3 | `REJECTED` |
  | 4 | `FAILED` / `TIMED_OUT` |
  | 5 | `ABSTAINED` / `PARTIAL` (incomplete) |
  | 6 | `CANCELLED` |

- **Output:**
  - The run ID, the terminal state, the artifact path, and `[FIXTURE]` for fake runs.
  - Historical-mode runs print the retrospective notice.
  - `configure_logging(settings)` is called once at startup.
- `replay` is wired to the M4-T03 behaviour. It is stubbed here only if M4-T03 has not landed,
  with a clear "not yet implemented" exit code of 2, not a fake success.
- **Do not:**
  - Put logic in the CLI. It calls services only.
  - Echo settings or credentials.
  - Make `execute` admit jobs.

## 2. Verify (before building)

- [ ] The runner API from M4-T01 exists as documented in its journal.
- [ ] The case manifests carry a question and a cutoff (`grep -n "question\|cutoff" eval_cases/manifests/*.json`).
      If they do not, report BLOCKED. Do not invent a question.
- [ ] Baseline: the four checks and `diagnose.py` are green.
- [ ] **Red first.** Write `test_cli_research.py`. Cover:
  - `seed` is idempotent: run twice, same state.
  - A fake run prints the run ID and `[FIXTURE]`, with exit 0.
  - `--case` and `--snapshot` together give exit 2.
  - `--snapshot` without `--question` gives exit 2.
  - A multi-instrument snapshot is rejected.
  - `status` and `cancel` work.
  - Exit codes per terminal state, using fake scripts.
  - A provider-key sentinel set in the environment is never in the output.

## 3. Build

1. Add `demo seed`.
2. Add the `research` sub-app: `run`, `status`, `execute`, `cancel`.
3. Add `replay`.
4. Add the exit-code mapping in one function.

## 4. Test

```bash
uv run pytest -q tests/integration/test_cli_research.py
uv run episalpha demo seed && uv run episalpha research run --case supported --runtime fake
uv run ruff check . && uv run ruff format --check . && uv run mypy src/episalpha && uv run pytest -q -m "not live"
```

Acceptance:
- [ ] The seed command is idempotent.
- [ ] Fake runs are labelled visibly.
- [ ] Output includes the run ID and artifact path.
- [ ] Exit codes distinguish success from rejected, failed and incomplete outcomes.
- [ ] No provider key appears in output.

## 5. Diagnose

- [ ] `diagnose.py`: no regression.
- [ ] Real CLI transcripts (fake runtime) are pasted in the journal.

## 6. Stop and hand off

- **BLOCKED if:** the case manifests lack the required fields.
- **Record:** M4 `PROGRESS.md`, `STATUS.md`, and the journal.
- **Next:** M4-T03.
