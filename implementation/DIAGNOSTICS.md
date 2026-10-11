# Diagnostics

Written by `uv run python scripts/diagnose.py`. Do not edit by hand; history is in
`logs/diagnose.jsonl`.

## Summary

- Verdict: **PASS**
- Timestamp: 2026-10-11T13:30:20+00:00
- Git HEAD: `1296edd` (dirty working tree)

## Checks

- `ruff check`: 0 violations {}
- `ruff format --check`: 0 files to reformat
- `mypy src/episalpha`: 0 errors
- `pytest -m "not live"`: {'passed': 632, 'failed': 0, 'errors': 0, 'skipped': 0}

## Tests by directory

| Directory | Passed | Failed | Errors | Skipped |
|---|---:|---:|---:|---:|
| contracts | 144 | 0 | 0 | 0 |
| evidence | 170 | 0 | 0 | 0 |
| integration | 58 | 0 | 0 | 0 |
| knowledge | 32 | 0 | 0 | 0 |
| observability | 17 | 0 | 0 | 0 |
| research | 74 | 0 | 0 | 0 |
| runtime | 118 | 0 | 0 | 0 |
| ui | 19 | 0 | 0 | 0 |

## Failing tests

- None.

## Traceability

- Missing files named by DONE rows: 0
- Tests no record mentions (orphans): 0
- STATUS.md vs PROGRESS.md mismatches: 0

## Regressions

- None.
