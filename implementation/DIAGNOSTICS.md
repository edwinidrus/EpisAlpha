# Diagnostics

_Not generated yet._ `scripts/diagnose.py` (task M0-T05) overwrites this file with the current
health snapshot on every run:

- the four standard checks;
- tests by directory;
- failing tests;
- traceability between the docs and the files on disk;
- regressions against the previous run.

History is kept in `logs/diagnose.jsonl`.
