# Diagnostics

Written by `uv run python scripts/diagnose.py`. Do not edit by hand; history is in
`logs/diagnose.jsonl`.

## Summary

- Verdict: **PASS**
- Timestamp: 2026-10-13T03:24:43+00:00
- Git HEAD: `061a7b6` (dirty working tree)

## Checks

- `ruff check`: 0 violations {}
- `ruff format --check`: 0 files to reformat
- `mypy src/episalpha`: 0 errors
- `pytest -m "not live"`: {'passed': 723, 'failed': 0, 'errors': 0, 'skipped': 8}

## Tests by directory

| Directory | Passed | Failed | Errors | Skipped |
|---|---:|---:|---:|---:|
| contracts | 144 | 0 | 0 | 0 |
| evaluation | 30 | 0 | 0 | 0 |
| evidence | 170 | 0 | 0 | 0 |
| evolution | 28 | 0 | 0 | 0 |
| integration | 83 | 0 | 0 | 8 |
| knowledge | 32 | 0 | 0 | 0 |
| observability | 17 | 0 | 0 | 0 |
| research | 74 | 0 | 0 | 0 |
| runtime | 120 | 0 | 0 | 0 |
| ui | 25 | 0 | 0 | 0 |

## Failing tests

- None.

## Traceability

- Missing files named by DONE rows: 0
- Tests no record mentions (orphans): 0
- STATUS.md vs PROGRESS.md mismatches: 0

## Regressions

- None.
