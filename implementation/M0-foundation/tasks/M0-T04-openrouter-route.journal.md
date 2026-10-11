# M0-T04 journal

## Attempt 1 — 2026-10-10 22:10 UTC — claude-opus-5-5
- Hypothesis: the OpenRouter `:free` route honours forced `tool_choice` the way glm-5.3 did, so
  the A3 relay design carries over unchanged.
- Owner approval: live calls approved, and the unconfirmed `:free` data-logging policy
  acknowledged, 2026-10-11 local time (AskUserQuestion answer "Approve + acknowledge"). The
  first probe invocation was interrupted by the owner at the tool prompt; the owner then
  re-confirmed "i just approve that please proceed" and the probe ran.
- Verify:
  - `.env` names (`cut -d= -f1 .env`) -> `ollama_api_key`, `alpha_vantage_api_key`,
    `openrouter_api_key`, `openrouter_model`. No values printed.
  - `grep '^openrouter_model' .env` -> `openrouter_model=nvidia/nemotron-3-ultra-550b-a55b:free`
  - Baseline: ruff -> All checks passed; format -> 34 files already formatted; mypy -> no issues
    in 20 source files; `pytest -m "not live"` -> 305 passed, 2 deselected.
  - Public listing `GET https://openrouter.ai/api/v1/models`: `:free` context_length 1000000,
    max_completion_tokens 65536, pricing 0/0, supported_parameters `include_reasoning, max_tokens,
    reasoning, reasoning_effort, seed, temperature, tool_choice, tools, top_p` (no
    `response_format`). Endpoints listing: one provider, `Nvidia`, uptime_last_30m 100.
- Did:
  - `scripts/probe_hermes.py`: `served_by`, `usage`, `NO_FALLBACKS` pin with a recorded
    fallback on 4xx, `response_format` HTTPError captured as `rejected_status`, `Retry-After`
    printed on errors.
  - `tests/integration/test_hermes_probe.py`: pins `served_by`; a recorded `rejected_status` is
    an accepted outcome; sends the pin when the lock says it was accepted. Forced-tool-choice
    assertions unchanged.
  - `config/demo.toml`, `config/demo.example.toml`: route switched; glm-5.3 kept as a history
    comment.
  - `config/runtime.lock.json`: new `model_route`; old one moved to `model_route_history[0]`
    with every field preserved (checked against `git show HEAD:`).
  - `docs/implementation/hermes_probe.md` §8 "Route change (A9)".
  - `tests/contracts/test_settings.py`: `test_example_config_loads` hard-coded `"glm-5.3"`, so it
    failed after the approved config switch: `AssertionError: assert
    'nvidia/nemot...50b-a55b:free' == 'glm-5.3'`. Changed it to compare the example config with the lock's
    `model_route` (model and endpoint), which is a stronger invariant and keeps model names out
    of test code (article 25). Outside the pack's file list; recorded here for that reason.
- Ran:
  - `uv run python scripts/probe_hermes.py config/demo.toml` (2026-10-10T22:18:33Z) -> exit 0;
    `finish_reason: tool_calls`, `forced_tool_choice_honored: true`,
    `arguments_parse_as_json: true`, keys `assertions, stance`, `served_by: Nvidia`,
    `no_fallbacks_accepted: true`, usage prompt 411 / completion 213 / reasoning 122 / cost 0,
    `response_format.json_schema_honored: true`.
  - `uv run pytest -q -m live tests/integration/test_hermes_probe.py` (2026-10-10T22:19:18Z) ->
    `2 passed in 11.36s`
  - Four standard checks after the change -> All checks passed; 34 files already formatted;
    no issues in 20 source files; 305 passed, 2 deselected.
- Outcome: PASS
- Findings:
  - `response_format` returned JSON on one call, unlike glm-5.3. The parameter is not listed for
    `:free`, so this is recorded as observed but weak; the relay stays tool_choice-only (A3).
    If a later live run sees prose, the lock value is stale and must be re-probed, not relaxed.
  - Reasoning tokens are reported inside `completion_tokens`. Whether `max_tokens` caps them was
    not probed.
  - Limits: 4000 tokens/call is comfortable for a trivial call (213 used); re-measure at M3-T02.
    8 requests/run at 50/day gives at most 6 runs/day.
  - No 429 seen; free-tier limits remain unprobed.
  - Live requests spent: 4 (probe 2, live tests 2).
- Decision: route verified; task DONE. Next M0-T05.
- Diagnose: `scripts/diagnose.py` n/a (M0-T05 not built); no spans (M0-T06 not built).
