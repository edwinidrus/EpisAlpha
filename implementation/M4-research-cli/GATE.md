# Gate G4: end-to-end research, CLI and replay

**Status:** PARTIAL 2026-10-11. Offline criteria passed; the three real-case reviews are BLOCKED on
the G2 owner checkpoint (M4-T04).

## Commands

```bash
uv run episalpha demo seed
uv run episalpha research run --case supported --runtime fake
uv run pytest -q tests/research tests/integration/test_cli_research.py
uv run python scripts/diagnose.py
# plus the four standard checks, and the three real-case reviews from M4-T04
```

## Criteria

- [x] The fake runtime covers completion, abstention, invalid references, provider failure,
      timeout, cancellation and partial output, each with the correct terminal state.
- [x] A repeated admission key returns the same run. Only one active job.
- [x] The CLI interface exactly matches plan §10 M4-T02. Exit codes are distinct, fake runs are
      labelled, and no key appears.
- [x] Replay makes zero provider or connector calls. Tampering gives `INTEGRITY_ERROR`.
      `research recover` creates a new attempt.
- [ ] Three real-case reviews are recorded in `docs/implementation/demo_acceptance.md`, with
      actual run IDs, hashes, usage and unknowns.
- [ ] Every number in each real thesis traces to a span or a recomputed derivation (A8).
- [x] A run's full story is one trace, in Phoenix or in `spans.jsonl` by trace ID: `research.run`
      → `snapshot.freeze` → `stage.*` (with `model.call` and `tool.*`) → `validation` →
      `repair.attempt` → `run.persist`. The CLI prints the trace ID.

## Results log (append-only; real output only)

### 2026-10-11 07:15 UTC — PARTIAL (offline PASSED; real-case reviews BLOCKED)

```
uv run episalpha demo seed                                   -> seeded: entities 4, instruments 4, documents 1, spans 2
uv run episalpha research run --case supported --runtime fake -> [FIXTURE] ... state: RESEARCH_COMPLETED (exit 0)
uv run pytest -q tests/research tests/integration/test_cli_research.py -> 97 passed
uv run python scripts/diagnose.py                            -> diagnose: PASS | tests 553 passed | failures 0 | regressions 0 | orphans 0
uv run ruff check . / ruff format --check . / mypy src/episalpha -> clean / formatted / no issues in 35 source files
```

Open:
- **Three real-case reviews (M4-T04):** BLOCKED. The case mapping is PROVISIONAL until the G2
  owner checkpoint (live ingestion and hand inspection) is done.
- **"Every number in each real thesis traces to a span or a recomputed derivation":** the
  mechanism is in place and tested (the runner validates every derived claim through M1-T05),
  but it cannot be shown on real theses until M4-T04 runs.

