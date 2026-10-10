# M3-T03 — Hermes adapter and frozen research harness

| Field | Value |
|---|---|
| Status | TODO |
| Depends on | M3-T02 |
| Phase constitution | [../CONSTITUTION.md](../CONSTITUTION.md) (inherits [global](../../CONSTITUTION.md)) |
| Plan source | plan §9 M3-T03 card, §3.6 stages 3–7; A5 |
| Journal | `tasks/M3-T03-hermes-adapter.journal.md` |
| Live calls | Yes. One staged run on the active route, about 8 requests or fewer. Owner approval required. |

## 0. Context to load

Load these and nothing else:
- `implementation/CONSTITUTION.md`
- `implementation/M3-runtime/CONSTITUTION.md`, articles 1, 5, 9, 10 and 11
- `config/runtime.lock.json`, `hermes.observed_controls` and `custom_tool_injection_finding`
- `docs/implementation/hermes_probe.md`, the controls table
- The M3-T01 journal (MCP proof trace) and the M3-T02 journal (Hermes endpoint evidence)
- `src/episalpha/runtime/port.py`, `tools.py` and `model_relay.py`
- `src/episalpha/contracts/research.py`: `StageResult`, `RuntimeContext`, `Thesis`,
  `ThesisAssertion`

Controls verified on `run_agent.AIAgent` at `c1488ac`:
- toolsets: `enabled_toolsets` / `disabled_toolsets`
- fresh profile: `skip_memory`, `skip_context_files`, `load_soul_identity`, `session_id`
- budgets: `max_iterations`, `iteration_budget`, `max_tokens`
- tracing: `event_callback`
- cancellation: `interrupt()` / `clear_interrupt()` / `close()`
- usage: `get_activity_summary()`
- routing: `base_url` / `api_key` / `provider` / `api_mode` / `model`

`fallback_model` and `providers_*` **must stay unset**.

## 1. Plan

- **Goal:** `HermesRuntime` implements `ResearchRuntimePort` on pinned Hermes, with three
  stages: researcher, critic and synthesizer. Each stage runs in a fresh context. Hermes reaches
  only the EpisAlpha MCP tools and the relay, and every stage output is a parseable candidate
  or an explicit error.
- **Files:**
  - `src/episalpha/runtime/hermes.py`. This is the **only** module importing Hermes; untyped
    imports are isolated here.
  - `harnesses/baseline/researcher.md`, `critic.md`, `synthesizer.md` and `config.json`. These
    are short prompt assets, not code. `config.json` starts as
    `{"schema_version": "1", "contradiction_search": false}`, as in plan §12.2.
  - Focused tests:
    - `tests/runtime/test_hermes_adapter.py`, an offline protocol test with a stub agent;
    - `tests/integration/test_hermes_runtime.py`, marked `live`.
- **Build behaviour:**
  - The agent is built with `base_url` = the relay, `api_key` = the per-run relay token,
    `model` = the route `model_id`, `enabled_toolsets=['episalpha']` and `skip_memory=True`.
    Session IDs are unique per stage.
  - Disable delegation, shell, browser, file access and unrelated plugins.
  - **Assert that the effective tool list equals the allowlist** before the first turn.
  - Final output arrives through a forced `submit_<stage>` tool whose arguments are the
    candidate JSON. It is parsed host-side. A malformed payload gives
    `StageResult(completed=False, exit_reason="INVALID_OUTPUT: …")`, never a quiet accept.
  - The critic receives the validated claim IDs plus eligible evidence through
    `RuntimeContext`. It receives no conversational memory from the researcher.
  - Usage comes from `get_activity_summary()`, plus relay counters. Unknown stays `None`.
  - The harness hash is the SHA-256 over the sorted harness files. It is recorded in each
    `StageResult` exit metadata or trace.
- **Out of scope:**
  - The container and network boundary (M3-T04).
  - Persistence and the repair loop (M4-T01 owns the bounded repair).
- **Do not:**
  - Pass any canonical DB handle or label path to Hermes.
  - Write prompts that instruct Hermes to "avoid lookahead". Lookahead is enforced by tools, not
    prompts.
  - Hard-code the model name.

## 2. Verify (before building)

- [ ] Re-confirm the pinned commit and the controls exist: `python -c` introspection inside the
      Hermes environment. Journal the result.
- [ ] The M3-T01 MCP proof is recorded as passing, and the M3-T02 relay is green.
- [ ] Owner approval for the live run is recorded, along with the free-tier requests left
      today.
- [ ] **Red first.** Write `test_hermes_adapter.py` with a stub `AIAgent`. Cover:
  - The allowlist mismatch abort.
  - Malformed submit arguments give `INVALID_OUTPUT`.
  - A fresh `session_id` per stage.
  - The critic's input excludes the researcher transcript.
  - Fallback fields are unset.
  - `stage.transition` events are emitted.

## 3. Build

1. Write the adapter skeleton and the untyped-import quarantine (`# type: ignore[import-untyped]`
   at the import line only).
2. Write the stage runner: build the agent, assert the tools, run, extract the submit arguments,
   build the `StageResult`.
3. Write the harness prompt files. Keep each under 60 lines, and require span-ID citations and
   explicit unknowns.
4. Write the live test: one synthetic snapshot, all three stages, asserting that the cited span
   IDs exist in the snapshot and that the outputs parse.

## 4. Test

```bash
uv run pytest -q tests/runtime
set -a; . ./.env; set +a
uv run pytest -q -m live tests/integration/test_hermes_runtime.py
uv run ruff check . && uv run ruff format --check . && uv run mypy src/episalpha && uv run pytest -q -m "not live"
```

Acceptance:
- [ ] The real workflow cites fixture span IDs, preserves unknowns, and produces parseable stage
      outputs.
- [ ] The critic receives validated claims plus eligible evidence, not uncontrolled
      conversational memory.
- [ ] Malformed output is returned as an error, not quietly accepted.
- [ ] The effective tool list is verified against the allowlist, and recorded.
- [ ] mypy strict is still clean. Hermes typing gaps are confined to `runtime/hermes.py`.

## 5. Diagnose

- [ ] `diagnose.py`: no regression.
- [ ] The journal has, for the live run: the effective tools, `served_by`, the harness hash,
      requests and tokens per stage, and the stage durations.
- [ ] Event check: three `stage.transition`, N `model.call` and M `tool.call` events, with no
      prompt text in the logs.

## 6. Stop and hand off

- **BLOCKED if:**
  - a required control is missing at the pin;
  - the live run is not approved;
  - the daily cap is exhausted;
  - Hermes ignores the forced submit tool on this route.
- **Record:** M3 `PROGRESS.md`, `STATUS.md`, and the journal.
- **Next:** M3-T04.
