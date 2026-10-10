# M0-T05 — Implementation diagnostics script (A11)

| Field | Value |
|---|---|
| Status | TODO |
| Depends on | M0-T01 |
| Phase constitution | [../CONSTITUTION.md](../CONSTITUTION.md) (inherits [global](../../CONSTITUTION.md)) |
| Plan source | amendment A11; plan §4.3 (the four standard checks) |
| Journal | `tasks/M0-T05-diagnose-script.journal.md` |

## 0. Context to load

Load these and nothing else:
- `implementation/CONSTITUTION.md`, article VII
- `implementation/M0-foundation/CONSTITUTION.md`, articles 6 and 7
- `implementation/README.md`, the session protocol and status values
- `implementation/STATUS.md`, plus one phase `PROGRESS.md` (to see the table format the script
  parses)
- `pyproject.toml`, the `[tool.pytest.ini_options]`, `[tool.ruff]` and `[tool.mypy]` sections
- `scripts/probe_hermes.py`, house style for a stdlib script

## 1. Plan

- **Goal:** one command, `uv run python scripts/diagnose.py`, that produces three things:
  - a white-box health picture in `implementation/DIAGNOSTICS.md`;
  - one JSON line appended to `implementation/logs/diagnose.jsonl`;
  - a non-zero exit when any check fails or regresses against the previous line.
- **In scope:**
  1. **Run the four standard checks** as subprocesses and parse them:
     - `ruff check --output-format=json`: count of violations by rule code.
     - `ruff format --check`: list of files that would be reformatted.
     - `mypy src/episalpha`: error count from the `Found N errors` or `Success` line.
     - `pytest -q -m "not live" --junitxml=<tmp>`: pass, fail, error and skip counts per test
       directory (`tests/<dir>`), plus the names of failing tests.
  2. **Traceability, comparing docs with disk:**
     - For every `DONE` row in a phase `PROGRESS.md`, each backticked path in the Changes column
       that looks like a repo file (`src/`, `tests/`, `scripts/`, `config/`, `apps/`, `docs/`)
       must exist. Report the missing ones.
     - Every `tests/**/test_*.py` must be mentioned in some `PROGRESS.md` or task pack.
       Unmentioned tests are reported as orphans.
     - `STATUS.md` statuses must equal the phase `PROGRESS.md` statuses. Report any mismatch.
  3. **Regression check:** compare against the last line of `diagnose.jsonl`. A regression is
     any of: fewer passed tests, more failures, more ruff or mypy errors, a new missing file.
  4. **Output:**
     - Rewrite `DIAGNOSTICS.md` (timestamp UTC, git `HEAD` short hash, dirty flag, every section
       above).
     - Append the JSON line.
     - Exit `0` when there is no failure and no regression, `1` otherwise.
     - The `--no-run` flag skips the subprocess checks and does traceability only, for speed.
- **Out of scope:**
  - Coverage measurement (no new dependency).
  - Live tests.
  - Editing any source.
  - CI integration.
- **Files:** `scripts/diagnose.py` + `tests/integration/test_diagnose.py`.
- **Produces:** pure, testable functions, with `main()` only wiring them together:
  - `parse_ruff_json(text)`
  - `parse_mypy(text)`
  - `parse_junit(xml_text)`
  - `progress_rows(markdown)`
  - `missing_files(rows, root)`
  - `orphan_tests(root, docs_text)`
  - `regressions(previous, current)`
  - `render_markdown(report)`
- **Do not:**
  - Import `episalpha` (the script must work even when the package is broken).
  - Add dependencies.
  - Read `.env`.
  - Print environment variables.

## 2. Verify (before building)

- [ ] `uv run ruff check --output-format=json .` and `uv run pytest --junitxml=/tmp/x.xml -q -m "not live"`
      work in this repo. Paste the shortest proof into the journal.
- [ ] Baseline: the four standard checks are green. Record the counts.
- [ ] Write `tests/integration/test_diagnose.py` first against inline fixture strings: a ruff
      JSON sample, a mypy success line and a mypy error line, a junit sample with 1 failure and
      1 skip, a two-row PROGRESS table, and two report dicts for `regressions`. Run it; it fails
      because the module is missing.

## 3. Build

1. Write the parsers as pure functions over strings.
2. Write the traceability functions over a `root: Path`.
3. Write `regressions(previous: dict | None, current: dict) -> list[str]`. When `previous` is
   `None`, return an empty list.
4. Write `render_markdown(report) -> str`. Sections, in order: Summary (PASS/FAIL), Checks,
   Tests by directory, Failing tests, Traceability, Regressions.
5. In `main()`:
   - Run the subprocesses with `subprocess.run([...], capture_output=True, text=True)`, using
     `uv run` for each tool.
   - Load the tests through `importlib`, by path.

## 4. Test

```bash
uv run pytest -q tests/integration/test_diagnose.py
uv run python scripts/diagnose.py
uv run ruff check . && uv run ruff format --check . && uv run mypy src/episalpha && uv run pytest -q -m "not live"
```

Acceptance:
- [ ] Each parser is tested against a realistic sample, including its failure shapes.
- [ ] A seeded fake regression (previous report with more passed tests) is detected.
- [ ] Running the script on the real repo writes `implementation/DIAGNOSTICS.md` and appends
      exactly one line to `implementation/logs/diagnose.jsonl`. The JSON parses and has the keys
      `timestamp`, `git_head`, `dirty`, `checks`, `tests`, `traceability` and `regressions`.
- [ ] Traceability on the current repo reports **zero missing files** for the 12 migrated DONE
      rows. If it finds some, that is a real finding: record it, and do not edit the rows to
      hide it.
- [ ] The exit code is `0` on a green repo and `1` when a check fails. Test this through the
      pure functions, not by breaking the repo.
- [ ] The script runs in under 60 s on this repo. Record the measured time.

## 5. Diagnose

- [ ] The first real `diagnose.jsonl` line is the baseline for every later task. Quote its
      summary in the journal.
- [ ] Journal entry written.

## 6. Stop and hand off

- **BLOCKED if:** ruff or pytest cannot emit machine-readable output in this version. In that
  case record the version and the fallback considered.
- **Record:** M0 `PROGRESS.md`, `STATUS.md`, and the journal.
- **Next:** M0-T06.
