# Gate G2: evidence storage, connectors and snapshots

**Status:** PASSED, with an owner checkpoint outstanding (2026-09-20) · **reopened** by A8/A11
(M2-T05, M2-T06).

## Commands

```bash
uv run pytest -q tests/evidence
# plus the four standard checks, and uv run python scripts/diagnose.py
```

## Criteria

- [x] SQLite has WAL, foreign keys and busy timeout; assessments are versioned; idempotent run
      admission; FTS5 over spans.
- [x] Content-addressed store with read-time verification; deterministic normalization; exact
      spans.
- [x] Price and filings connectors work offline over an injected transport. A refusal is
      `SOURCE_FAILED`; empty is `NO_DATA`.
- [x] Snapshot hash is deterministic, with a closed `SnapshotView`; future-source and
      source-failure synthetic cases are present.
- [ ] **A8:** point-in-time XBRL facts. A post-cutoff restatement is never selected, and
      `frames` is never called (M2-T05).
- [ ] **A11:** every connector request, response and refusal emits a redacted event (M2-T06).
- [ ] **Owner checkpoint:** live ingestion of LULU, TSCO and CALX, with key quotations inspected
      by hand. The case mapping moves from PROVISIONAL to confirmed.

## Results log (append-only; real output only)

### 2026-09-20 — PASSED (owner checkpoint outstanding)

```
uv run pytest -q tests/evidence   -> 139 passed
uv run ruff check .               -> All checks passed
uv run ruff format --check .      -> 34 files already formatted
uv run mypy src/episalpha         -> Success: no issues found in 20 source files
uv run pytest -q -m "not live"    -> 305 passed, 2 deselected
```

**Schema note.** `SnapshotManifest` gained `source_completeness`, a tuple defaulting to empty.
The change is additive and backward compatible, so schema version stays `1`.
