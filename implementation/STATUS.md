# Status rollup

Execution order runs top to bottom. **Next task: `M5-T04`.** Detail, real command output and
blockers live in each phase's `PROGRESS.md`. Update both files when a task changes state.

| # | Task | Title | Status | Depends on | Pack |
|---:|---|---|---|---|---|
| 1 | M0-T01 | Bootstrap owned application | DONE | — | — |
| 2 | M0-T02 | Resolve settings and record execution state | DONE | M0-T01 | — |
| 3 | M0-T03 | Probe official Hermes and one model route | DONE | M0-T02 | — |
| 4 | M0-T02b | Source model expansion (A2) | DONE | M0-T02 | — |
| 5 | M1-T01 | Knowledge contracts | DONE | G0 | — |
| 6 | M1-T02 | Research contracts, lifecycle, errors | DONE | M1-T01 | — |
| 7 | M1-T03 | Temporal eligibility policy | DONE | M1-T02 | — |
| 8 | M1-T04 | Structural evidence and graph validator | DONE | M1-T03 | — |
| 9 | M2-T01 | SQLite persistence and migration | DONE | G1 | — |
| 10 | M2-T02 | Content-addressed payloads and exact spans | DONE | M2-T01 | — |
| 11 | M2-T03 | Narrow source adapters | DONE | M2-T02 | — |
| 12 | M2-T04 | Frozen snapshot builder and demo corpus | DONE | M2-T03 | — |
| 13 | M0-T04 | Research route moves to OpenRouter (A9) | DONE | M0-T03 | [pack](M0-foundation/tasks/M0-T04-openrouter-route.md) |
| 14 | M0-T05 | Implementation diagnostics script (A11) | DONE | M0-T01 | [pack](M0-foundation/tasks/M0-T05-diagnose-script.md) |
| 15 | M0-T06 | OpenTelemetry observability foundation (A11, A14) | DONE | M0-T02 | [pack](M0-foundation/tasks/M0-T06-observability.md) |
| 16 | M0-T07 | Local Arize Phoenix diagnose service (A14) | DONE | M0-T06 | [pack](M0-foundation/tasks/M0-T07-phoenix.md) |
| 17 | M1-T05 | Derivation registry and recomputation (A8) | DONE | G1 | [pack](M1-contracts/tasks/M1-T05-derivations.md) |
| 18 | M2-T05 | Point-in-time XBRL fundamentals (A8) | DONE | M2-T03, M1-T05 | [pack](M2-evidence/tasks/M2-T05-xbrl.md) |
| 19 | M2-T06 | Instrument connectors with spans (A11, A14) | DONE | M0-T06, M2-T05 | [pack](M2-evidence/tasks/M2-T06-connector-events.md) |
| 20 | M3-T01 | Runtime port, fake runtime, typed tools (+A12/A13 hooks) | DONE | G2, M2-T05, M2-T06 | [pack](M3-runtime/tasks/M3-T01-port-and-tools.md) |
| 21 | M3-T02 | Single-route model relay (+A12/A13 hooks) | DONE | M3-T01, M0-T04 | [pack](M3-runtime/tasks/M3-T02-model-relay.md) |
| 21b | M3-T02b | MCP tool server and stage candidate schemas (split from M3-T03) | DONE | M3-T02 | [pack](M3-runtime/tasks/M3-T02b-mcp-server.md) |
| 22 | M3-T03 | Hermes adapter and frozen research harness (+A12/A13 hooks) | DONE | M3-T02b | [pack](M3-runtime/tasks/M3-T03-hermes-adapter.md) |
| 23 | M3-T04 | Whole-worker isolation and watchdog (+A12/A13 hooks) | DONE | M3-T03 | [pack](M3-runtime/tasks/M3-T04-isolation.md) |
| 24 | M4-T01 | Research runner and job lifecycle (+A12/A13 hooks) | DONE | G3 | [pack](M4-research-cli/tasks/M4-T01-runner.md) |
| 25 | M4-T02 | CLI commands | DONE | M4-T01 | [pack](M4-research-cli/tasks/M4-T02-cli.md) |
| 26 | M4-T03 | Replay and recovery semantics | DONE | M4-T02 | [pack](M4-research-cli/tasks/M4-T03-replay-recovery.md) |
| 27 | M4-T04 | Real thesis quality review | BLOCKED | M4-T03 | [pack](M4-research-cli/tasks/M4-T04-quality-review.md) |
| 28 | M5-T01 | Browser shell and research view | DONE | G4 | [pack](M5-browser-obsidian/tasks/M5-T01-browser-shell.md) |
| 29 | M5-T02 | Evidence inspection and local graph | DONE | M5-T01 | [pack](M5-browser-obsidian/tasks/M5-T02-evidence-graph.md) |
| 30 | M5-T03 | Deterministic Obsidian exporter | DONE | M5-T02 | [pack](M5-browser-obsidian/tasks/M5-T03-obsidian-export.md) |
| 30a | M0-T08 | Portable offline Docker stack (A15) | DONE | M5-T03 | [pack](M0-foundation/tasks/M0-T08-portable-docker.md) |
| 30b | **M3-T05** | Compose sandbox topology (A15) | **DONE** | M0-T08 | [pack](M3-runtime/tasks/M3-T05-compose-topology.md) |
| 31 | M5-T04 | Browser walkthrough and usability correction | TODO | M5-T03 | [pack](M5-browser-obsidian/tasks/M5-T04-walkthrough.md) |
| 32 | M6-T01 | Labeled cases and deterministic metrics | TODO | G5 | [pack](M6-evaluation/tasks/M6-T01-cases-metrics.md) |
| 33 | M6-T02 | Candidate validation and lineage | TODO | M6-T01 | [pack](M6-evaluation/tasks/M6-T02-candidates.md) |
| 34 | M6-T03 | Offline campaign runner | TODO | M6-T02 | [pack](M6-evaluation/tasks/M6-T03-campaign.md) |
| 35 | M6-T04 | Experiment report and browser comparison | TODO | M6-T03 | [pack](M6-evaluation/tasks/M6-T04-report.md) |
| 36 | M7-T01 | Cross-boundary acceptance suite | TODO | G6 | [pack](M7-acceptance/tasks/M7-T01-acceptance-suite.md) |
| 37 | M7-T02 | Demo packaging and smoke command | TODO | M7-T01 | [pack](M7-acceptance/tasks/M7-T02-smoke.md) |
| 38 | M7-T03 | Final owner walkthrough | TODO | M7-T02 | [pack](M7-acceptance/tasks/M7-T03-walkthrough.md) |
| 39 | M8-T01 | Skill library and ledger (A13, post-v0.1) | TODO | G7 | [pack](M8-learning/tasks/M8-T01-skill-library.md) |
| 40 | M8-T02 | Harvest and deterministic screening (A13) | TODO | M8-T01 | [pack](M8-learning/tasks/M8-T02-screening.md) |
| 41 | M8-T03 | Offline paired skill evaluation (A13) | TODO | M8-T02 | [pack](M8-learning/tasks/M8-T03-evaluation.md) |
| 42 | M8-T04 | Promotion, revocation, temporal availability (A13) | TODO | M8-T03 | [pack](M8-learning/tasks/M8-T04-promotion.md) |
| 43 | M8-T05 | Trace-grounded improvement backlog (A14) | TODO | G7, M0-T07 | [pack](M8-learning/tasks/M8-T05-trace-backlog.md) |

## Gates

| Gate | Status | Detail |
|---|---|---|
| G0 | **PASSED 2026-10-10** (re-run after A9/A11/A14) · owner review of probe findings outstanding | [M0 GATE](M0-foundation/GATE.md) |
| G1 | **PASSED 2026-10-10** (re-run after A8) · owner review of serialized examples outstanding | [M1 GATE](M1-contracts/GATE.md) |
| G2 | **PASSED 2026-10-10** (re-run after A8/A11/A14) · owner checkpoint (live ingestion + hand inspection) outstanding | [M2 GATE](M2-evidence/GATE.md) |
| G3 | **PASSED 2026-10-11 (re-run after A15)** · owner TODOs: rootless Docker / userns-remap; macOS/Windows checks | [M3 GATE](M3-runtime/GATE.md) |
| G4 | **PARTIAL 2026-10-11**: offline passed; real-case reviews BLOCKED on the G2 owner checkpoint | [M4 GATE](M4-research-cli/GATE.md) |
| G5–G7 | Not started | phase `GATE.md` files |
| G8 | Not started (post-v0.1 learning loop, A13) | [M8 GATE](M8-learning/GATE.md) |

A reopened gate is re-run, with real output recorded, once its new tasks are DONE. Earlier
results stay in the log; they are not overwritten.
