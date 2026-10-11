# M4-T01 journal

## Attempt 1 — 2026-10-11 06:40 UTC — claude-opus-5-5
- Verify:
  - G3 recorded PASSED (`implementation/M3-runtime/GATE.md`, 2026-10-11).
  - Interfaces: `Repository.admit_run`, `save_stage_result`, `update_run`, `stage_results`;
    `check_transition` / `RunRecord.transition`; `build_snapshot`, `build_view`; `validate`,
    `failed_checks`, `RecordSet`. **Missing:** lease and cancel storage, so an additive
    migration was needed.
  - Baseline: four checks green, 504 passed.
  - Red first: `tests/research/test_runner.py` written before the runner ->
    `ModuleNotFoundError: No module named 'episalpha.research.runner'`.
- Did:
  - `src/episalpha/research/runner.py`: `Evidence`, `admit` (idempotent; one active job),
    `claim` (atomic lease via the `run_lease` primary key), `request_cancel`,
    `cancel_requested`, `ResearchRunner` (`execute`, `tools_for`, `brief_for` for the Hermes
    runtime). Candidate keys map to canonical `<run_id>.<key>`; an existing ID is refused;
    each stage is validated with the M1 validator (references, quotations, derivations); one
    bounded repair per run (stage re-run with the failures in the brief); honest terminal
    states; persist-then-declare; lease released at the end.
  - `src/episalpha/research/artifacts.py`: `RunArtifacts` (canonical JSON, atomic writes,
    SHA-256 index with the trace ID, snapshot hash, harness and skill-set hashes and runtime
    label; `read` verifies, `verify` lists tampered files). Stage payloads are kept per attempt,
    before repair.
  - `src/episalpha/storage/migrations/002_jobs.sql`: `run_lease`, `run_cancel`. Additive.
    **Schema compatibility decision:** the database version goes 1 -> 2; existing databases
    migrate forward; contract `SCHEMA_VERSION` stays 1. Two M2-T01 tests that hard-coded the
    latest version (`== 1`) now expect 2 and also check the new tables.
  - **Bug found in M2-T01 code and fixed:** `Repository.update_run` used `INSERT OR REPLACE`,
    which deletes and re-inserts the run row. With foreign keys on, `ON DELETE CASCADE`
    silently wiped the run's `stage_result` rows (and its lease) on every state change. Found
    because `test_completion` saw `stage_results == []`. Now an `UPDATE` with a rowcount check;
    regression test `test_updating_a_run_keeps_its_stage_results` added. `stage_results` now
    orders by `started_at, rowid` (insertion order), so equal timestamps no longer fall back to
    alphabetical stage order.
  - `src/episalpha/runtime/fake.py`: list scripts (successive attempts), `Scenario.REPAIRED`,
    `model_id = "fixture"`; `tests/fixtures/runtime/repaired.json`.
  - `src/episalpha/runtime/hermes.py`: the inner span is renamed `sandbox.run` (CHAIN), because
    the runner now owns `stage.<name>` (M4 constitution article 9). Adapter test updated.
- Ran:
  - `uv run pytest -q tests/research/test_runner.py` -> first run `3 failed, 15 passed` (the
    cascade bug), then `18 passed` after the fix and the ordering change.
  - `uv run pytest -q tests/evidence/test_repository.py tests/research/test_runner.py` -> `45
    passed`.
  - Four checks: All checks passed; formatted; no issues in 34 source files; `523 passed, 8
    deselected`.
- The story of a run (fake COMPLETION, `spans.jsonl`, sorted by start; one trace):
  ```
  research.run           CHAIN     instrument synthetic-issuer.eq, runtime fake, historical_reconstruction
  snapshot.freeze        CHAIN     snapshot.run-0001, hash 08bd2aa1…8c16, documents/spans/claims counts
  stage.researching      AGENT     attempt 1, exit completed, model_requests 2
  stage.critiquing       AGENT     attempt 1, exit completed, model_requests 2
  stage.synthesizing     AGENT     attempt 1, exit completed, model_requests 2
  validation             EVALUATOR 12 check events, disposition RESEARCH_COMPLETED, failed_checks 0, unresolved_reviews 2
  run.persist            CHAIN     records 5, state RESEARCH_COMPLETED
  ```
  The root `research.run` carries `episalpha.state`, reason, error code and usage totals.
- Outcome: PASS
