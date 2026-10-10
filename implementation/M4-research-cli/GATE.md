# Gate G4: end-to-end research, CLI and replay

**Status:** not started.

## Commands

```bash
uv run episalpha demo seed
uv run episalpha research run --case supported --runtime fake
uv run pytest -q tests/research tests/integration/test_cli_research.py
uv run python scripts/diagnose.py
# plus the four standard checks, and the three real-case reviews from M4-T04
```

## Criteria

- [ ] The fake runtime covers completion, abstention, invalid references, provider failure,
      timeout, cancellation and partial output, each with the correct terminal state.
- [ ] A repeated admission key returns the same run. Only one active job.
- [ ] The CLI interface exactly matches plan §10 M4-T02. Exit codes are distinct, fake runs are
      labelled, and no key appears.
- [ ] Replay makes zero provider or connector calls. Tampering gives `INTEGRITY_ERROR`.
      `research recover` creates a new attempt.
- [ ] Three real-case reviews are recorded in `docs/implementation/demo_acceptance.md`, with
      actual run IDs, hashes, usage and unknowns.
- [ ] Every number in each real thesis traces to a span or a recomputed derivation (A8).
- [ ] A run's full story can be reconstructed from `episalpha.jsonl` alone, filtered by
      `run_id`: snapshot built, then stages, then validation, then repair, then terminal.

## Results log (append-only; real output only)

_No runs yet._
