# M4-T01 — Research runner and job lifecycle

| Field | Value |
|---|---|
| Status | DONE |
| Depends on | G3 |
| Phase constitution | [../CONSTITUTION.md](../CONSTITUTION.md) (inherits [global](../../CONSTITUTION.md)) |
| Plan source | plan §10 M4-T01 card, §3.6 (stages, state machine, background execution), §3.7 |
| Journal | `tasks/M4-T01-runner.journal.md` |

## 0. Context to load

Load these and nothing else:
- `implementation/CONSTITUTION.md`
- `implementation/M4-research-cli/CONSTITUTION.md`
- [../PLAN.md](../PLAN.md), the interface table
- `src/episalpha/contracts/research.py`, the whole file
- `src/episalpha/storage/repository.py:317-437`, the run, snapshot and stage methods
- `src/episalpha/evidence/snapshots.py`, `build_snapshot` and `build_view`
- `src/episalpha/research/validation.py`, `validate` and `RecordSet`
- `src/episalpha/runtime/port.py` and `fake.py`
- `src/episalpha/observability.py`

> Stages: 1. Validate request and admit idempotently. 2. Freeze eligible evidence and market
> context. 3. Researcher produces claims and candidate hypotheses. 4. Validate references before
> passing them to later stages. 5. Critic checks counter-evidence and missing information in a
> fresh context. 6. Synthesizer creates `Thesis` from validated intermediate records. 7. Run
> deterministic validation; allow one bounded schema/reference repair. 8. Persist completed
> research, abstention, partial result, or explicit failure. (plan §3.6)

> Network failures after partial work must preserve that work while recording failed/incomplete
> status. Never silently translate a provider outage into a valid abstention. (plan §3.6)

## 1. Plan

- **Goal:** one runner drives a run through the eight stages on any `ResearchRuntimePort`. It
  persists every transition and checkpoint, and always ends in an honest terminal state.
- **Files:**
  - `src/episalpha/research/runner.py`
  - `src/episalpha/research/artifacts.py`
  - Focused test: `tests/research/test_runner.py`
- **Produces:**
  - `admit(request: RunRequest) -> RunRecord`. It is idempotent on the key, and a second active
    job gives `INVALID_REQUEST`.
  - `claim(run_id, worker_id) -> RunRecord`. An atomic lease; a second claim fails.
  - `execute(run_id, runtime: ResearchRuntimePort) -> RunRecord`. Its sequence:
    1. Freeze the snapshot.
    2. If essential evidence is missing, the result is `ABSTAINED`, with a next inquiry.
    3. Run the researcher stage, then validate references and map candidate IDs to canonical
       IDs.
    4. Run the critic stage, with validated records only.
    5. Run the synthesizer stage.
    6. Run `validate()`, then at most one repair, then persist.
  - `request_cancel(run_id)`. A persisted flag that the watchdog observes.
  - `artifacts.py` writes, hashes and indexes the run artifacts: manifest, generated records,
    stage payloads, validation report and thesis.
  - It also keeps the **pre-repair candidate payload** of each stage. M6-T01's numeric-correctness
    metric (A8) compares the model-proposed numbers *before* repair against the recomputed
    values, so the pre-repair numbers must survive.
  - Worker output is read under M3 constitution article 14 (A12): regular files only, no
    symlinks, size caps, schema validation.
  - Persist the run's `propose_skill` proposals as artifacts, with `run_id`, stage and cited
    span IDs, so the M8 loop can harvest them with provenance. Record the **skill-set hash**
    on the run.
- **ID mapping:**
  - Candidate-local IDs are mapped host-side to new canonical IDs.
  - A candidate attempting to reuse an existing canonical ID is rejected.
  - Mapped records reach later stages only through `RuntimeContext.validated_*`.
- **Errors to terminal states:**

  | Condition | Terminal state |
  |---|---|
  | Provider failure, 429 or relay error | `FAILED`, with partial artifacts kept |
  | Watchdog | `TIMED_OUT` |
  | Cancel flag | `CANCELLED` |
  | Unrepairable invalid output | `REJECTED` |
  | Did real work but not all of it | `PARTIAL` |

- **Spans (A11, A14), one trace per run, inside `bind_run(run_id)`:**
  - root `research.run` (`CHAIN`), which carries the terminal state, reason and usage totals
    as attributes;
  - children: `snapshot.freeze`, `stage.<name>` (`AGENT`), `validation` (`EVALUATOR`, with one
    span event per check), `repair.attempt`, `sandbox.run`, `run.persist`;
  - model and tool spans from the relay and tools (M3) nest under the active stage span;
  - the trace ID is persisted in the run's artifact index.
- **Out of scope:**
  - CLI (M4-T02).
  - Replay and recovery (M4-T03).
  - UI.
  - The `contradiction_search` step (M6-T03).
- **Do not:**
  - Bypass `check_transition`.
  - Mark a stage complete before persisting.
  - Reset budgets between stages.

## 2. Verify (before building)

- [ ] G3 is recorded as passed, or the BLOCKED live parts are clearly separated in
      `../../M3-runtime/GATE.md`.
- [ ] The interfaces exist with the stated signatures
      (`grep -n "def admit_run\|def save_stage_result\|def check_transition\|def build_snapshot\|def validate" -r src/episalpha`).
- [ ] Baseline: the four checks and `diagnose.py` are green.
- [ ] **Red first.** Write `tests/research/test_runner.py` with `FakeRuntime` scripts. Cover:
  - Completion.
  - Abstention, when essential evidence is missing.
  - Invalid references repaired once.
  - Invalid references unrepairable, giving `REJECTED`.
  - Provider failure gives `FAILED`, not `ABSTAINED`, with partial artifacts kept.
  - Timeout.
  - Cancellation.
  - A partial result.
  - The same idempotency key gives the same run.
  - A second active job is refused.
  - A double claim is refused.
  - An interrupted stage never shows as completed.
  - A canonical-ID overwrite attempt is rejected.
  - The event sequence for one completed run.

## 3. Build

1. Write admission and claim on the repository, in short transactions.
2. Write the stage loop with persisted checkpoints.
3. Write ID mapping and the reference validation between stages.
4. Write final validation, the repair, the terminal state, and the artifacts.

## 4. Test

```bash
uv run pytest -q tests/research/test_runner.py
uv run ruff check . && uv run ruff format --check . && uv run mypy src/episalpha && uv run pytest -q -m "not live"
```

Acceptance:
- [ ] The fake runtime covers completion, abstention, invalid references, provider failure,
      timeout, cancellation and partial artifacts.
- [ ] A repeated admission key returns the same run.
- [ ] Interrupted stages cannot claim successful completion.
- [ ] The event trail for each scenario matches its terminal state.

## 5. Diagnose

- [ ] `diagnose.py`: no regression.
- [ ] Paste one complete event trail (fake run, `jq`-filtered by `run_id`) into the journal as
      the reference "story of a run".

## 6. Stop and hand off

- **BLOCKED if:** a needed repository operation is missing. Add it only within this task's file
  budget, or split the task.
- **Record:** M4 `PROGRESS.md`, `STATUS.md`, and the journal.
- **Next:** M4-T02.
