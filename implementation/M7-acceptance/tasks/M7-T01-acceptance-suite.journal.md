# M7-T01 journal — Cross-boundary acceptance suite

## Attempt 1 — 2026-10-13 — claude-opus-5-5
- Verify: G6 is PARTIAL (offline passed, live campaign BLOCKED); continued on the owner's
  2026-10-12 "full auto" instruction, recorded in `docs/implementation/progress.md`. Baseline
  green (699). The existing tests per row were inventoried before writing code, but the map
  below was written into this journal afterwards, not before: a process deviation.
- First run: `25 passed, 5 failed`. Every failure was in the new test, none in a module:
  A02 (`claims` is a mapping), A08 (no `ToolHost.tool_names`; rewritten against
  `STAGE_READ_TOOLS` and a real `search_evidence`), A13 (lineage is in the run index, not the CLI
  text), A25 (`model_copy` does not validate a string into `Decimal`), A07 (two CLI runs of the
  same case and runtime are one request by design, so the "repaired" run was the rejected one;
  the test now uses another case). Then A20's object-store check was made unconditional (it sat
  behind `if exists`, which could have skipped silently). `30 passed`.
- No production module changed in this task.

### Row-to-test map (final), `tests/integration/test_demo_acceptance.py`

| Row | Boundary driven | Lower-level proof |
|---|---|---|
| A01 | CLI run -> knowledge drilldown: every assertion's claims reach passages inside the manifest | `test_runner.py::test_completion`, `test_query.py` |
| A02 | CLI run (conflicting) -> recorded assessment -> `run_view` review chip; both claims kept | `test_query.py`, UI tests |
| A03 | runner with empty evidence -> ABSTAINED, "Next inquiry", 0 model requests | `test_runner.py::test_missing_essential_evidence_abstains_before_any_stage` |
| A04 | runner with a failed source -> FAILED / SOURCE_FAILED; CLI status shows it | `test_snapshots.py`, `test_connectors.py` |
| A05 | later document saved -> CLI replay passes, snapshot and run tree hash unchanged | `test_replay.py::test_later_evidence_...` |
| A06 | runner freezes v1 (T1) not v2 (T3) at cutoff T2 | `test_snapshots.py::test_a_cutoff_between_versions_...` |
| A07 | CLI: invalid references -> REJECTED/INVALID_OUTPUT; repaired -> completed with warning | `test_runner.py` repair tests |
| A08 | injected text returned verbatim as data by `search_evidence`; stage tool surface is read-only + submit + propose_skill | `test_connectors.py::test_ingestion_strips_active_content_from_the_text`, UI inert-text test |
| A09 | `worker_command` with real settings paths: only spec and out mounted | `test_sandbox.py::test_nothing_forbidden_reaches_the_worker` |
| A10 | CLI: timeout -> exit 4, usage and stage history kept; cancel -> execute exit 6 | `test_runner.py`, `test_cli_research.py` |
| A11 | AppTest submit + reruns + a new session -> one run, one launch | `test_research_view.py` |
| A12 | CLI replay with runtime, fake stages and relay forwarding all patched to raise | `test_replay.py` |
| A13 | CLI snapshot rerun -> new run ID, `prior_run_id` in index, prior run tree unchanged | `test_cli_research.py` |
| A14 | validator: SUPPORTS from a span and a dangling CONTRADICTS both fail | `test_validation.py` |
| A15 | CLI export twice -> same generated tree hash, annotation intact, every link resolves | `test_obsidian_export.py` |
| A16 | `propose` with a budget patch -> rejected and in the ledger | `test_candidates.py` |
| A17 | real abstained fake run scored against "answer required" labels -> completion 0/1, recall 0/1 | `test_scoring.py` |
| A18 | CLI `experiment compare` -> `baseline_retained`; report says "complete, valid result" | `test_campaign.py`, `test_reporting.py` |
| A19 | services execute with a crashing runtime -> state CRITIQUING; CLI recover -> completes, interrupted attempt kept | `test_replay.py::test_a_crash_...` |
| A20 | edited thesis artifact -> CLI replay exit 4 INTEGRITY_ERROR; tampered object -> `ObjectIntegrityError` | `test_replay.py`, `test_objects_and_spans.py` |
| A21 | fixture knowledge with a copied release -> drilldown shows one shared lineage | `test_query.py` |
| A22 | CLI status "tokens ... unknown, cost unknown"; `eur_cap` refused at load | `test_settings.py`, UI tests |
| A23 | CLI notice line; `run_view.notice`; executed after the cutoff | UI tests |
| A24 | changed label -> new campaign ID and manifest; old manifest untouched | `test_campaign.py` |
| A25 | validator recomputes 0.03, refuses claimed 0.10 | `test_derivations.py`, `test_validation.py` |
| A26 | sentinel key in env; run, status, replay, export; every file under data root and the vault scanned | `test_observability.py`, CLI tests |
| A27 | relay HTTP front on loopback refuses plugins, models, `:online`, web_search; provider never called | `test_model_relay.py` |
| A28 | HermesRuntime + stdlib fake worker writing `state.db` -> flagged; no `hermes-home` left | `test_hermes_adapter.py` |
| A29 | `read_worker_json` refuses a symlink and a 70 KB file | `test_hermes_adapter.py` |
| A32 | OTLP endpoint on a closed loopback port: run completes; one trace holds freeze, stage, validation, persist; no secret, no evidence text in `spans.jsonl` | `test_observability.py` |

Not automated (listed in `GATE.md`): A11 a real browser refresh; A15 Obsidian opening the vault;
A32 the trace in a running Phoenix (`tests/integration/test_phoenix_export.py`, live marker);
A09/A27/A28 against the real container, relay route and Hermes (live boundary tests exist and
were run in M3 with owner approval). A30–A31 belong to G8.

- Ran: `uv run pytest -q tests/integration/test_demo_acceptance.py` -> `30 passed`; four checks
  green; `diagnose.py` -> `PASS | tests {'passed': 729, ...} | regressions 0 | orphans 0`.
- Outcome: PASS (offline). No fixture is labelled live.
