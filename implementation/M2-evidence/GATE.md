# Gate G2: evidence storage, connectors and snapshots

**Status:** PASSED 2026-10-10 (re-run after A8/A11/A14) · the owner checkpoint (live ingestion
and hand inspection of LULU, TSCO, CALX) is still outstanding.

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
- [x] **A8:** point-in-time XBRL facts. A post-cutoff restatement is never selected, and
      `frames` is never called (M2-T05).
- [x] **A11:** every connector request, response and refusal emits a redacted `connector.fetch`
      span (M2-T06).
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

### 2026-10-10 23:15 UTC — re-run after A8/A11/A14: PASSED (owner checkpoint outstanding)

```
uv run pytest -q tests/evidence   -> 168 passed
uv run ruff check .               -> All checks passed!
uv run ruff format --check .      -> 44 files already formatted
uv run mypy src/episalpha         -> Success: no issues found in 23 source files
uv run pytest -q -m "not live"    -> 399 passed, 3 deselected
uv run python scripts/diagnose.py -> diagnose: PASS | tests 399 passed | failures 0 | regressions 0 | orphans 0
```

The owner checkpoint is still open: the live ingestion of the three real cases and the hand
inspection of their key quotations. The case mapping stays PROVISIONAL, and M4-T04 depends on it.
