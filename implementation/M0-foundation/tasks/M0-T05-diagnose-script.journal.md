# M0-T05 journal

## Attempt 1 — 2026-10-10 22:25 UTC — claude-opus-5-5
- Hypothesis: a stdlib script can run the four checks, parse machine-readable output and trace
  PROGRESS rows to disk without importing `episalpha`.
- Verify:
  - `uv run ruff --version` -> `ruff 0.16.8`; `uv run ruff check --output-format=json .` -> `[]`
  - `uv run pytest --junitxml=<scratch>/x.xml -q -m "not live"` -> `305 passed, 2 deselected`;
    the XML has `<testsuite ... tests="305">` with `classname="tests.contracts.test_knowledge"`.
  - Baseline four checks: All checks passed; 34 files already formatted; no issues in 20 source
    files; 305 passed, 2 deselected.
  - Red first: `uv run pytest -q tests/integration/test_diagnose.py` -> `19 errors`
    (FileNotFoundError: `scripts/diagnose.py` missing).
- Did:
  - `scripts/diagnose.py`: parsers (`parse_ruff_json`, `parse_mypy`, `parse_format_check`,
    `parse_junit`), traceability (`progress_rows`, `status_rows`, `missing_files`,
    `orphan_tests`, `status_mismatches`), verdict (`regressions`, `failures`, `exit_code`),
    `render_markdown`, `main`.
  - `tests/integration/test_diagnose.py`: 19 tests on inline samples.
- Decisions:
  - Missing files and STATUS/PROGRESS mismatches count as failures (exit 1); orphan tests are
    reported only.
  - `DONE_OFFLINE` rows are traced like `DONE`.
  - The regression baseline for a full run is the last line that has checks, so a `--no-run`
    line never hides a test-count drop.
  - Unparseable tool output (`None`) is a failure, never a pass.
- Ran:
  - `uv run pytest -q tests/integration/test_diagnose.py` -> `19 passed in 0.05s`
  - `time uv run python scripts/diagnose.py` -> `diagnose: PASS | tests {'passed': 324, 'failed':
    0, 'errors': 0, 'skipped': 0} | failures 0 | regressions 0 | orphans 0 | 4.5s`, exit 0,
    `real 0m4.598s`; `diagnose.jsonl` 0 -> 1 line.
  - Traceability is not vacuous: 43 rows, 13 DONE, 41 backticked repo paths checked, 0 missing.
- Outcome: PASS
- Diagnose: first baseline line written (324 passed: contracts 144, evidence 139, integration
  21, research 20). No spans yet (M0-T06).
