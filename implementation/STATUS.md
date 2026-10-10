# Status rollup

Execution order runs top to bottom. **Next task: `M0-T04`.** Detail, real command output and
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
| 13 | **M0-T04** | Research route moves to OpenRouter (A9) | **TODO** | M0-T03 | [pack](M0-foundation/tasks/M0-T04-openrouter-route.md) |
| 14 | M0-T05 | Implementation diagnostics script (A11) | TODO | M0-T01 | [pack](M0-foundation/tasks/M0-T05-diagnose-script.md) |
| 15 | M0-T06 | Runtime observability foundation (A11) | TODO | M0-T02 | [pack](M0-foundation/tasks/M0-T06-observability.md) |
| 16 | M1-T05 | Derivation registry and recomputation (A8) | TODO | G1 | [pack](M1-contracts/tasks/M1-T05-derivations.md) |
| 17 | M2-T05 | Point-in-time XBRL fundamentals (A8) | TODO | M2-T03, M1-T05 | [pack](M2-evidence/tasks/M2-T05-xbrl.md) |
| 18 | M2-T06 | Instrument connectors with events (A11) | TODO | M0-T06, M2-T05 | [pack](M2-evidence/tasks/M2-T06-connector-events.md) |
| 19 | M3-T01 | Runtime port, fake runtime, typed tools | TODO | G2, M2-T05, M2-T06 | [pack](M3-runtime/tasks/M3-T01-port-and-tools.md) |
| 20 | M3-T02 | Single-route model relay | TODO | M3-T01, M0-T04 | [pack](M3-runtime/tasks/M3-T02-model-relay.md) |
| 21 | M3-T03 | Hermes adapter and frozen research harness | TODO | M3-T02 | [pack](M3-runtime/tasks/M3-T03-hermes-adapter.md) |
| 22 | M3-T04 | Whole-worker isolation and watchdog | TODO | M3-T03 | [pack](M3-runtime/tasks/M3-T04-isolation.md) |
| 23 | M4-T01 | Research runner and job lifecycle | TODO | G3 | [pack](M4-research-cli/tasks/M4-T01-runner.md) |
| 24 | M4-T02 | CLI commands | TODO | M4-T01 | [pack](M4-research-cli/tasks/M4-T02-cli.md) |
| 25 | M4-T03 | Replay and recovery semantics | TODO | M4-T02 | [pack](M4-research-cli/tasks/M4-T03-replay-recovery.md) |
| 26 | M4-T04 | Real thesis quality review | TODO | M4-T03 | [pack](M4-research-cli/tasks/M4-T04-quality-review.md) |
| 27 | M5-T01 | Browser shell and research view | TODO | G4 | [pack](M5-browser-obsidian/tasks/M5-T01-browser-shell.md) |
| 28 | M5-T02 | Evidence inspection and local graph | TODO | M5-T01 | [pack](M5-browser-obsidian/tasks/M5-T02-evidence-graph.md) |
| 29 | M5-T03 | Deterministic Obsidian exporter | TODO | M5-T02 | [pack](M5-browser-obsidian/tasks/M5-T03-obsidian-export.md) |
| 30 | M5-T04 | Browser walkthrough and usability correction | TODO | M5-T03 | [pack](M5-browser-obsidian/tasks/M5-T04-walkthrough.md) |
| 31 | M6-T01 | Labeled cases and deterministic metrics | TODO | G5 | [pack](M6-evaluation/tasks/M6-T01-cases-metrics.md) |
| 32 | M6-T02 | Candidate validation and lineage | TODO | M6-T01 | [pack](M6-evaluation/tasks/M6-T02-candidates.md) |
| 33 | M6-T03 | Offline campaign runner | TODO | M6-T02 | [pack](M6-evaluation/tasks/M6-T03-campaign.md) |
| 34 | M6-T04 | Experiment report and browser comparison | TODO | M6-T03 | [pack](M6-evaluation/tasks/M6-T04-report.md) |
| 35 | M7-T01 | Cross-boundary acceptance suite | TODO | G6 | [pack](M7-acceptance/tasks/M7-T01-acceptance-suite.md) |
| 36 | M7-T02 | Demo packaging and smoke command | TODO | M7-T01 | [pack](M7-acceptance/tasks/M7-T02-smoke.md) |
| 37 | M7-T03 | Final owner walkthrough | TODO | M7-T02 | [pack](M7-acceptance/tasks/M7-T03-walkthrough.md) |

## Gates

| Gate | Status | Detail |
|---|---|---|
| G0 | Offline PASSED · live PARTIAL · **reopened** by A9 (route change) and A11 (M0-T05/T06) | [M0 GATE](M0-foundation/GATE.md) |
| G1 | PASSED · **reopened** by A8 (M1-T05) | [M1 GATE](M1-contracts/GATE.md) |
| G2 | PASSED with an owner checkpoint outstanding · **reopened** by A8/A11 (M2-T05/T06) | [M2 GATE](M2-evidence/GATE.md) |
| G3–G7 | Not started | phase `GATE.md` files |

A reopened gate is re-run, with real output recorded, once its new tasks are DONE. Earlier
results stay in the log; they are not overwritten.
