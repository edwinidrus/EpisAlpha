# M4-T03 journal

## Attempt 1 — 2026-10-11 07:05 UTC — claude-opus-5-5
- Verify:
  - The artifact index records a hash for every artifact type (manifest, stages, records,
    validation, thesis, proposals).
  - Baseline: four checks green, 544 passed.
  - Red first: `tests/research/test_replay.py` written first -> `ImportError: cannot import
    name 'replay' from 'episalpha.research.artifacts'`. One test-side fix:
    `SemanticAssessment` takes `reviewer_identity`, not `reviewer_id`.
- Did:
  - `src/episalpha/research/artifacts.py`: `replay()` returning `ReplayView`, in a `replay`
    span. **Chain of trust:** every artifact must match `index.json`, and the manifest and
    thesis must also equal the canonical SQLite records, so a consistent edit of an artifact
    *and* its index entry is still caught (tested). `verify_snapshot` and the index state are
    checked as well. The index is now rewritten after every artifact write, so a crashed run
    leaves a verifiable partial record.
  - `src/episalpha/research/runner.py`:
    - Before calling the runtime, each stage attempt is saved as `completed=False,
      exit_reason="started"`, so a process killed mid-call leaves a visible incomplete attempt.
    - `execute(..., resume=True)` rebuilds counters and history, re-accepts completed stages
      from their saved payloads through the same host validation (no runtime call), re-opens
      the run's own snapshot (it must still match), and runs the interrupted stage as attempt
      N+1.
    - `recover()` removes the stale lease explicitly, re-claims and resumes; finished runs are
      refused.
    - `lineage` (`prior_run_id`) goes into the index.
  - `src/episalpha/research/services.py`: `recover_run`, `replay_run`,
    `prior_run_for_snapshot`; snapshot reruns record their prior run.
  - `src/episalpha/cli.py`: `research recover RUN_ID`; `replay RUN_ID` (exit 0 verified, 4
    integrity error, 2 unknown run); `_fail` now also shuts tracing down. A test-isolation bug:
    an error exit left a configured tracer behind for the next test.
  - Tests: `tests/research/test_replay.py` (7), plus 3 CLI tests replacing the replay stub test.
- Lineage: no `prior_run_id` field was added to `RunRequest` (that would be a contract change).
  Lineage lives in `submission.json` and the artifact index, and replay prints it.
- Ran: `uv run pytest -q tests/integration/test_cli_research.py tests/research` -> `97
  passed`; four checks green, `553 passed, 8 deselected`. The replay test asserts no
  `model.call` and no `connector.*` spans, and patches `ModelRelay.__init__`,
  `HttpTransport.__call__` and `FakeRuntime.run_stage` to raise.
- Real CLI transcript (fake runtime, demo config):
```
[FIXTURE] fake runtime: scripted fixture output, not research
replay: run-15b0260c2fac (8 artifacts verified, no model or network calls)
state: RESEARCH_COMPLETED
reason: research completed and validated
notice: Retrospective research; model training knowledge may include later events.
stance: watch
- [observation] Fourth quarter revenue was reported at EUR 412.0 million. (run-15b0260c2fac.c1)
- [interpretation] Management's softer demand outlook may precede weaker revenue. (run-15b0260c2fac.c2, run-15b0260c2fac.h1)
- [bear_case] Reported revenue so far shows no decline. (run-15b0260c2fac.c1)
- [invalidation] Next quarter revenue at or above EUR 412.0 million would falsify the mechanism. (run-15b0260c2fac.h1)
missing: Order-book size for the first half is not disclosed in the snapshot.
missing: Order-book size for the first half.
snapshot: snapshot.run-15b0260c2fac 162cc9b4b490a32e0fadea848a5630652e2cc11115deec40427b9658b6033e8d
trace: ce97682657ae2a393377aca9ed0652f1
exit=0
error: INVALID_REQUEST: run 'run-15b0260c2fac' already ended as RESEARCH_COMPLETED; nothing to recover
exit=2
```
- Outcome: PASS
