# M2 progress

One row per task. A task is DONE only when its acceptance checks actually pass, with the real
command output recorded here. Keep `../STATUS.md` in step. Commits are an owner action.

Rows for completed tasks were migrated unchanged from `docs/implementation/progress.md` on
2026-10-10 (amendment A10).

| Task | Status | Changes | Verification | Blocker | Next |
|---|---|---|---|---|---|
| M2-T01 | DONE | `src/episalpha/storage/db.py`, `repository.py`, `migrations/001_initial.sql`, `tests/evidence/test_repository.py` — typed node registry so relation endpoints are real foreign keys; WAL, FK enforcement, busy timeout, explicit transactions; versioned assessments; runs with a unique idempotency key; stage checkpoints and usage; FTS5 over spans kept in step by triggers. | 2026-09-20: `uv run pytest -q tests/evidence/test_repository.py` → 26 passed | None | M2-T02 |
| M2-T02 | DONE | `src/episalpha/storage/objects.py`, `src/episalpha/evidence/parsing.py`, `tests/evidence/test_objects_and_spans.py` — SHA-256 content-addressed store with atomic writes and read-time verification; deterministic NFC text normalization; script/style/comment content stripped; spans cut from the text so a quotation cannot be invented. | 2026-09-20: `uv run pytest -q tests/evidence/test_objects_and_spans.py` → 27 passed | None | M2-T03 |
| M2-T03 | DONE | `src/episalpha/connectors/prices.py`, `connectors/filings.py`, `tests/fixtures/connectors/*`, `tests/evidence/test_connectors.py` — Alpha Vantage daily prices and SEC EDGAR filings, both driven by an injected transport so the default suite is offline; EDGAR host allowlist and fair-access User-Agent. | 2026-09-20: `uv run pytest -q tests/evidence/test_connectors.py` → 32 passed | None | M2-T04 |
| M2-T04 | DONE | `src/episalpha/evidence/snapshots.py`, `eval_cases/manifests/*` (3 real), `eval_cases/development/*` (5 synthetic), `tests/evidence/test_snapshots.py` — deterministic content hash, closed `SnapshotView`, recorded source completeness. | 2026-09-20: `uv run pytest -q tests/evidence/test_snapshots.py` → 32 passed | Demo case mapping still PROVISIONAL; owner checkpoint pending | M1-T05 |
| M2-T05 | TODO | Planned (A8): `src/episalpha/connectors/xbrl.py`, `tests/fixtures/connectors/companyfacts_*.json`, `tests/evidence/test_xbrl.py` | — | — | M2-T06 |
| M2-T06 | TODO | Planned (A11): instrument `src/episalpha/connectors/prices.py`, `src/episalpha/connectors/filings.py`, `src/episalpha/connectors/xbrl.py`; `tests/evidence/test_connector_events.py` | — | — | M3-T01 |
