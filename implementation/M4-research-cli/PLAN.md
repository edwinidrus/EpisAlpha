# M4 plan: end-to-end research, CLI and replay

**Goal:** a complete vertical slice before UI work. A run can be admitted, executed, validated
and persisted, then replayed and recovered, all from the CLI. Three real theses are reviewed.

**Plan source:** plan §10 (M4-T01..T04), §3.6, §3.7; acceptance rows A01–A03, A05, A07, A10,
A12, A13, A19 and A20.

## Tasks

| Task | Title | Status | Depends on | Pack |
|---|---|---|---|---|
| M4-T01 | Research runner and job lifecycle | TODO | G3 | [pack](tasks/M4-T01-runner.md) |
| M4-T02 | CLI commands | TODO | M4-T01 | [pack](tasks/M4-T02-cli.md) |
| M4-T03 | Replay and recovery semantics | TODO | M4-T02 | [pack](tasks/M4-T03-replay-recovery.md) |
| M4-T04 | Real thesis quality review | TODO | M4-T03 | [pack](tasks/M4-T04-quality-review.md) |

## Existing interfaces this phase builds on

| Name | Location |
|---|---|
| `RunState`, `allowed_transitions`, `check_transition`, `RunRecord.transition` | `src/episalpha/contracts/research.py:53-122, 311-352` |
| `RunRequest`, `Budgets`, `RuntimeContext`, `StageResult`, `Usage`, `ValidationReport` | `contracts/research.py` |
| `Repository.admit_run`, `update_run`, `run_by_idempotency_key`, `runs_in_state`, `save_stage_result`, `stage_results`, `run_usage`, `save_snapshot`, `get_snapshot` | `src/episalpha/storage/repository.py:317-437` |
| `build_snapshot`, `verify_snapshot`, `build_view` | `src/episalpha/evidence/snapshots.py` |
| `validate`, `RecordSet` | `src/episalpha/research/validation.py` |
| `ResearchRuntimePort`, `FakeRuntime`, `HermesRuntime`, `SandboxedWorker`, `ModelRelay` | `src/episalpha/runtime/*` (M3) |

## Free-tier note

M4-T04 needs three live cases at 8 requests or fewer each, so 24 or fewer requests. That fits
one day at 50/day. Check the remaining cap before starting, and record it.

## Precondition for M4-T04

The G2 owner checkpoint, live ingestion and inspection of LULU, TSCO and CALX, must be done.
Otherwise the real-case review rests on a provisional corpus, and M4-T04 is BLOCKED.
