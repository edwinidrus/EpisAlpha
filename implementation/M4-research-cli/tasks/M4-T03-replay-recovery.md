# M4-T03 — Replay and recovery semantics

| Field | Value |
|---|---|
| Status | DONE |
| Depends on | M4-T02 |
| Phase constitution | [../CONSTITUTION.md](../CONSTITUTION.md) (inherits [global](../../CONSTITUTION.md)) |
| Plan source | plan §10 M4-T03 card, §3.7; acceptance rows A05, A12, A13, A19, A20 |
| Journal | `tasks/M4-T03-replay-recovery.journal.md` |

## 0. Context to load

Load these and nothing else:
- `implementation/CONSTITUTION.md`
- `implementation/M4-research-cli/CONSTITUTION.md`, articles 4–6
- `src/episalpha/research/artifacts.py`, `runner.py` and `cli.py` (the files this task changes)
- `src/episalpha/storage/objects.py` (`ObjectIntegrityError`, read-time verification)
- `src/episalpha/evidence/snapshots.py`, `verify_snapshot`

> - **Saved artifact replay:** opens recorded tool results, model outputs, thesis, assessments,
>   and manifests. Makes zero model/network calls; historical content remains unchanged.
> - **Fresh inference:** creates a new run against a specified frozen snapshot. May produce
>   different results. Links to prior run rather than overwriting it.
> - **Recovery:** resumes deterministic completed stages. An interrupted model stage is recorded
>   as incomplete; explicitly restart it as a new attempt, preserving old attempt metadata.
>
> (plan §3.7)

## 1. Plan

- **Goal:** replay is network-free and tamper-evident, fresh inference is new lineage, and
  recovery is explicit and history-preserving.
- **Files:**
  - `src/episalpha/research/artifacts.py`
  - `src/episalpha/research/runner.py`
  - `src/episalpha/cli.py`, adding `research recover RUN_ID`
  - Focused test: `tests/research/test_replay.py`
- **Build:**
  - `replay(run_id) -> ReplayView`, which verifies every artifact hash and the snapshot hash.
    Any mismatch gives `INTEGRITY_ERROR`.
  - Fresh inference sets `prior_run_id` on a new run.
  - `recover(run_id)` creates attempt N+1. Completed deterministic stages are reused, never
    redone automatically. The interrupted model stage stays visible in attempt history.
- **Out of scope:** UI replay (M5).
- **Do not:**
  - Construct a provider client or connector in the replay path. Enforce this with a test that
    makes construction raise.

## 2. Verify (before building)

- [ ] The artifact index from M4-T01 records hashes for every artifact type.
- [ ] Baseline: the four checks and `diagnose.py` are green.
- [ ] **Red first.** Write `test_replay.py`. Cover:
  - Replay with the network blocked: patch the transport and relay to raise. It produces the
    same artifacts.
  - Ingesting later evidence or assessments does not change the replay.
  - Flipping one byte in an artifact gives `INTEGRITY_ERROR`.
  - Fresh inference gives a new run ID, with the prior run untouched.
  - A crash simulated mid model call is visible in attempt history after `recover`.
  - The `research recover` CLI exit codes.

## 3. Build

1. Write the replay reader with hash verification.
2. Write the lineage field and fresh-inference admission.
3. Write `recover` and the CLI command.

## 4. Test

```bash
uv run pytest -q tests/research/test_replay.py tests/integration/test_cli_research.py
uv run ruff check . && uv run ruff format --check . && uv run mypy src/episalpha && uv run pytest -q -m "not live"
```

Acceptance:
- [ ] Saved replay invokes no provider or connector.
- [ ] Later evidence or assessment changes do not change the replay.
- [ ] Tampering produces `INTEGRITY_ERROR`.
- [ ] A new inference gets a new run ID.
- [ ] A crash during a model call remains visible in attempt history.

## 5. Diagnose

- [ ] `diagnose.py`: no regression.
- [ ] The replay path emits **no** `model.call` and no `connector.*` events. Assert this in a
      test and note it in the journal.

## 6. Stop and hand off

- **BLOCKED if:** artifacts from M4-T01 lack hashes. That needs an M4-T01 fix first; record the
  dependency.
- **Record:** M4 `PROGRESS.md`, `STATUS.md`, and the journal.
- **Next:** M4-T04.
