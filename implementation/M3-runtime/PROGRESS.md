# M3 progress

One row per task. A task is DONE only when its acceptance checks actually pass, with the real
command output recorded here. Keep `../STATUS.md` in step. Commits are an owner action.

| Task | Status | Changes | Verification | Blocker | Next |
|---|---|---|---|---|---|
| M3-T05 | DONE | A15 host/compose topology, per-stage volume sub-paths, preflight and runtime wiring; `src/episalpha/runtime/sandbox.py`, `src/episalpha/research/services.py`, `tests/runtime/test_sandbox.py`, `tests/runtime/test_sandbox_services.py`, `tests/integration/test_runtime_boundary.py`, `config/runtime.lock.json`; constitution wording and G3 re-run; [pack](tasks/M3-T05-compose-topology.md), [journal](tasks/M3-T05-compose-topology.journal.md) | 2026-10-11: Task 4 sandbox 16 passed, Task 5 sandbox 17 passed / services 3 passed; four fresh Step 4 checks: All checks passed!, 83 files already formatted, Success: no issues found in 38 source files, 632 passed, 8 deselected in 15.11s. Both Task 5 topology probes: 3 passed each, only relay_via_forwarder ALLOWED; controller compose live run: 2 stages completed, synthesizer FAILED / SOURCE_FAILED (provider-side), 7 requests / 4 tool calls, 23611/461 tokens, six successful calls served_by Nvidia, no leftovers. Full live evidence quoted below. | No completed live thesis in compose yet; macOS/Windows owner checks pending; rootless Docker / userns-remap owner TODO. Supported case abstained because real filings are not ingested (G2 owner checkpoint). After-admission runtime assembly can strand QUEUED; recover with research recover; not fixed in A15. | M5-T04 |
| M3-T01 | DONE | `src/episalpha/runtime/port.py` (`ResearchRuntimePort`, `ExitReason`, `ToolResult`), `src/episalpha/runtime/tools.py` (`ToolHost`: 8 snapshot-bound tools incl. `compute_derivation` host-side and data-only `propose_skill`; one `tool.<name>` span per call), `src/episalpha/runtime/fake.py` (`FakeRuntime`, 7 labelled scenarios), `tests/fixtures/runtime/*.json`, `src/episalpha/settings.py` (skill-proposal limits), `tests/runtime/test_tools.py` (27 tests), `scripts/probe_mcp.py`; MCP proof recorded in `config/runtime.lock.json` | 2026-10-10/11: MCP proof on pinned Hermes 0.21.3 → model called `mcp__episalpha__echo_span` and returned the exact quote in 2 API calls (with `tools.tool_search.enabled: off`); `uv run pytest -q tests/runtime` → 27 passed; four checks green, `pytest -m "not live"` → 426 passed | None | M3-T02 |
| M3-T02 | DONE | `src/episalpha/runtime/model_relay.py` (`ModelRelay`: one route, field allowlist, model and tool checks, `max_tokens` clamp, run-global request budget, bounded transient retries, 429 within wall time, serialized upstream, cancel, usage with unknowns as None, `served_by`; SSE replay for the streaming worker; `RelayServer` stdlib front; `model.call` and `relay.refusal` spans), `tests/runtime/test_model_relay.py` (34 tests) | 2026-10-11: `uv run pytest -q tests/runtime` → 61 passed; four checks green, `pytest -m "not live"` → 460 passed; live: Hermes 0.21.3 (no key in its env) → relay → OpenRouter, tool called, exact quote returned, 2 requests, served_by Nvidia, 2862/120 tokens | None | M3-T03 |
| M3-T02b | DONE | `src/episalpha/runtime/mcp_server.py` (stdlib MCP Streamable-HTTP server, per-stage tool lists, first-submission-wins submit tools), `src/episalpha/runtime/candidates.py` (strict stage candidate schemas, inlined submit JSON schemas), `tests/runtime/test_mcp_server.py` (21 tests); fixture sections fixed (`bear_case`) | 2026-10-11: `uv run pytest -q tests/runtime/test_mcp_server.py` → 21 passed; pinned Hermes registered all 9 research tools over HTTP (no model call); four checks green, `pytest -m "not live"` → 481 passed | None | M3-T03 |
| M3-T03 | DONE | `worker/hermes_stage.py` (runs in the pinned Hermes env: lockdown config, MCP registration, allowlist check, interrupt after submit, no summary request), `src/episalpha/runtime/hermes.py` (`HermesRuntime`, `load_harness`, harness/skill-set hashes, hostile result reading, state.db row check), `harnesses/baseline/*` (3 stage prompts, contradiction-search block, config), `tests/runtime/test_hermes_adapter.py` (+ `tests/fixtures/runtime/fake_worker.py`), `tests/integration/test_hermes_runtime.py` (live); hooks: `observability.py` trace hand-off, `model_relay.py` `StagePolicy`, `tools.py` keyword search + result hashes, `settings.py` stage caps | 2026-10-11: `uv run pytest -q tests/runtime` → 97 passed (13 adapter); live `uv run pytest -q -m live tests/integration/test_hermes_runtime.py` → 1 passed (attempt 2; attempt 1 rejected a malformed synthesis as designed): 3 stages, 6 requests, served_by Nvidia, valid span citations, one trace 279e56da…; four checks green, 497 passed | None | M3-T04 |
| M3-T04 | DONE | `src/episalpha/runtime/sandbox.py` (hardened container launcher: internal network with no host address, fixed-target forwarder, no DNS, digest-pinned image, non-root, read-only rootfs, tmpfs caps, cap-drop ALL, no-new-privileges, pids/memory/CPU limits; watchdog and cancel with measured stop time; minimal-context image build), `container/Dockerfile`, `container/forwarder.py`, `src/episalpha/runtime/hermes.py` (launcher interface, `LocalLauncher`), `worker/hermes_stage.py` (home report), `tests/runtime/test_sandbox.py` (7), `tests/integration/test_runtime_boundary.py` (3 live), container variant in `tests/integration/test_hermes_runtime.py`; image ID in `config/runtime.lock.json` | 2026-10-11: boundary `uv run pytest -q -m live tests/integration/test_runtime_boundary.py` → 3 passed (every forbidden access BLOCKED, only the relay via forwarder ALLOWED; cancel 2.57 s, timeout 2.57 s); real-provider run in the container → 1 passed, 6 requests, served_by Nvidia, trace f8c7b412…; four checks green, 504 passed | Owner TODO: rootless Docker or userns-remap (rootful engine hardened only) | M4-T01 |

## M3-T05 — controller live evidence (2026-10-11, verbatim)

Controller-executed, owner-approved; not re-run by the Task 6 implementer. G3 boundary
verdicts are quoted in [GATE.md](GATE.md) and the linked journal from Task 5's same-day
**Answer 1 / continuation**. The new live trace is JSONL only, not a new Phoenix pass.

```text
# Task 6 live-run evidence (executed by the controller, owner-approved, 2026-10-11)

Environment: Linux host, Docker Engine 29.1.3 (API 1.52), Compose v5.0.1; compose topology;
EPISALPHA_PHOENIX_PORT=6007 (host 6006 used by another project); otlp_endpoint unset (spans → JSONL only).

## Attempt A — approved command, stale image
`docker compose -f compose.yaml -f compose.live.yaml run --rm cli research run --case supported --runtime hermes`
-> exit 1, `OSError: [Errno 99] Cannot assign requested address` in the relay's server_bind.
Root cause: episalpha-app:local was built in Task 2, before Tasks 4–5; the baked code still bound
the docker0 gateway. No model request was made. The crash left run-64371faa7c96 QUEUED (holding
the single job slot). Fix: `docker compose -f compose.yaml -f compose.live.yaml build`; inside the
rebuilt image `sandbox_config` reports `compose 0.0.0.0 /stages`.

## Attempt B — recover the stranded run (same request)
`docker compose -f compose.yaml -f compose.live.yaml run --rm cli research recover run-64371faa7c96`
-> exit 5, state ABSTAINED, reason "essential evidence missing: no eligible documents at the research
cutoff. Next inquiry: ingest the filings for this instrument and cutoff.", usage model requests 0,
tool calls 0, trace 2fe7fdd04060962745f6a783257b9f26. (The case's real filings are not ingested on
this machine — G2 owner checkpoint.) The worker was never launched.

## Attempt C — owner re-approved: synthetic snapshot
`docker compose -f compose.yaml -f compose.live.yaml run --rm cli research run --snapshot snapshot.run-53a5b38d52ae --question "Did the company change full-year guidance, and what did it attribute the change to?" --runtime hermes`
-> exit 4, run-3e482d7c5938, state FAILED, reason "synthesizing: provider_failure: SOURCE_FAILED",
error_code SOURCE_FAILED, usage: model requests 7, tool calls 4, tokens 23611/461, cost unknown,
trace 1c8801aa415db157bc92bbcc1046dd4d.
Stage results: RESEARCHING completed (4 requests, 3 tool calls); CRITIQUING completed (2, 1);
SYNTHESIZING not completed, provider_failure: SOURCE_FAILED (1, 0).
model.call spans: 6 × http 200, outcome ok, served_by Nvidia; the 7th: http 200 with span status
ERROR (relay rejected the 200 body; OpenRouter error-in-200 pattern) → SOURCE_FAILED, honestly not an
abstention. After the run: `docker ps -a --filter name=episalpha-worker- --filter name=episalpha-fwd-`
→ none (no leftovers).

## Conclusion for M3-T05
The compose topology's live path is exercised end to end on Linux: worker in the compose sandbox,
forwarder → relay and MCP tool server by name, stage files via the episalpha-stages sub-paths, two
completed stages, honest terminal state. The synthesizer failure is provider-side. Not verified:
a completed live thesis in compose; macOS / Windows (owner checks).
Finding for the final review: a runtime-assembly failure AFTER admission (e.g. relay bind error)
strands the run in QUEUED holding the job slot; preflight now catches the common causes before
admission, but not this class.
```

## M3-T05 — final Step 6 checks

`uv run ruff check . && uv run ruff format --check . && uv run mypy src/episalpha && uv run pytest -q -m "not live" && uv run python scripts/diagnose.py`
(exit 0):

```text
All checks passed!
83 files already formatted
Success: no issues found in 38 source files
632 passed, 8 deselected in 16.08s
diagnose: PASS | tests {'passed': 632, 'failed': 0, 'errors': 0, 'skipped': 0} | failures 0 | regressions 0 | orphans 0 | 16.9s
```
