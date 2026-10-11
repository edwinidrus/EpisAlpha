# M4 constitution: end-to-end research, CLI and replay

Inherits [../CONSTITUTION.md](../CONSTITUTION.md). The articles below add to it and never relax it.

1. **Honest terminal states.**
   - `RESEARCH_COMPLETED`, `ABSTAINED`, `PARTIAL`, `REJECTED`, `FAILED`, `CANCELLED` and
     `TIMED_OUT` each mean exactly what plan §3.6 says.
   - Every terminal state records reason, warnings, usage and artifact references.
   - A provider outage or 429 is `FAILED`, never `ABSTAINED`.
2. **Transitions go through the contract.** Every state change goes through
   `check_transition` / `RunRecord.transition` (`contracts/research.py`). There are no ad-hoc
   state writes.
3. **Admission is idempotent, with one job.**
   - The same idempotency key returns the same run.
   - At most one active research job.
   - Worker claims are atomic; a stale lease needs explicit recovery.
4. **Persist before declaring.** A stage is complete only after its `StageResult` and artifacts
   are persisted. An interrupted model stage stays incomplete in attempt history.
5. **Replay makes zero calls.** Saved-artifact replay invokes no provider and no connector, and
   verifies hashes. Tampering gives `INTEGRITY_ERROR`, never silent regeneration.
6. **Fresh inference is new lineage.** A new run ID links to the prior run. Nothing is
   overwritten.
7. **Exactly one bounded repair.** The repair targets schema and reference errors only. It never
   relaxes a validator and never touches human-owned annotations or labels.
8. **The CLI never leaks.**
   - No provider key appears in output.
   - Fake runs are labelled visibly.
   - Exit codes distinguish success, rejected, failed and incomplete.
9. **Orchestration emits the pure modules' spans (A11, A14).**
   - The runner owns the run's trace: root span `research.run` (`CHAIN`), with
     `session.id` = `run_id`.
   - It emits these on behalf of the pure modules, which stay pure:
     - `snapshot.freeze`, with the snapshot hash and counts;
     - `stage.<name>` (`AGENT`);
     - `validation` (`EVALUATOR`), with one span event per check, the disposition, the
       failed-check count and unresolved reviews;
     - `repair.attempt`.
   - The terminal state, reason and usage totals are set as attributes on `research.run`.
   - The trace ID is stored with the run's artifacts, so any run opens in Phoenix.
10. **Quality failures are feedback, not permission.** A poor real thesis is recorded and
    attributed. Validators are never weakened to pass a review.
