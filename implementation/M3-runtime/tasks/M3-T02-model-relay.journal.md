# M3-T02 journal

## Attempt 1 — 2026-10-11 05:55 UTC — claude-opus-5-5
- Hypothesis: a small stdlib relay can serve exactly what pinned Hermes sends, holding the key,
  enforcing every budget, and refusing every internet channel.
- Verify:
  - `config/runtime.lock.json` -> `model_route.verified: true` (OpenRouter, M0-T04),
    `observed_capabilities.no_fallbacks_accepted: true`. `reasoning` is not verified, so it is
    not forwarded.
  - **Hermes endpoint evidence, with zero model requests.** A loopback logging stub stood in for
    the provider, and the M3-T01 MCP driver pointed Hermes 0.21.3 at it (`base_url` = stub,
    `api_key` = a fake run token). Hermes sent:
    - `GET /api/v1/models` (three times), `GET /v1/models/nvidia/nemotron-3-ultra-550b-a55b:free`,
      `GET /v1/models`, `POST /api/show {"name": ...}`: metadata probes;
    - `POST /v1/chat/completions` with keys `['max_tokens', 'messages', 'model', 'stream',
      'stream_options', 'tools']`, `stream: true`, `stream_options: {"include_usage": true}`, no
      `tool_choice`, `User-Agent: OpenAI/Python 2.24.0`.
  - Second capture with every probe answered `404`: Hermes still ran the turn (the tool call
    was executed and the final answer produced, 2 chat calls). So the relay serves one path
    and 404s the rest.
  - **Streaming.** Hermes streams by default (`agent/turn_api_call.py::_should_stream`); the only
    switch is the private attribute `agent._disable_streaming`. Decision: do not depend on a
    private attribute. The relay calls the provider without streaming and replays the finished
    completion as SSE (two chunks plus `[DONE]`, tool calls carrying `index`). The stub proved
    Hermes' OpenAI client accepts exactly this, including a tool call.
  - OpenInference names read from the pinned Phoenix source: `llm.model_name`,
    `llm.token_count.prompt|completion|total`, `llm.token_count.completion_details.reasoning`.
  - Baseline: four checks green, 426 passed. Red first: `ModuleNotFoundError: No module named
    'episalpha.runtime.model_relay'`.
- Did:
  - `src/episalpha/runtime/model_relay.py`: `prepare` (pure validation: size, JSON, field
    allowlist, model, tool names, `max_tokens` clamp, `provider.allow_fallbacks: false`),
    `to_sse`, `ModelRelay` (`forward`, `cancel`, `usage`, `served_by`, `failure`,
    `requests_used`), `HttpTransport` (stdlib `http.client`, closeable), `RelayServer` (stdlib
    `ThreadingHTTPServer` front, bearer run token). `model.call` LLM span per upstream attempt;
    `relay.refusal` span for refusals before any upstream call. Relay-made errors never carry
    the provider body, and returned and traced bodies are scrubbed of the key.
  - `tests/runtime/test_model_relay.py`: 34 tests.
- Decisions:
  - No `httpx`: stdlib `http.client` is enough, since no streaming is needed upstream (plan open
    question 3).
  - Relay errors are HTTP 400 (404 for unserved paths, 413 oversize, 499 cancelled), so the
    worker's OpenAI client does not multiply requests with its own retries. `relay.failure`
    tells the runner why (`SOURCE_FAILED`, `BUDGET_EXCEEDED`), so a provider outage is never
    read as an abstention.
  - A 429 without `Retry-After`, or one longer than the remaining wall time, is
    `SOURCE_FAILED` (a found edge: with no deadline it would otherwise have waited forever;
    test added).
  - `max_tokens` is clamped, not rejected, and always set.
- Ran:
  - `uv run pytest -q tests/runtime/test_model_relay.py` -> `34 passed`;
    `uv run pytest -q tests/runtime` -> `61 passed`
  - Four checks: All checks passed; 52 files formatted; no issues in 28 source files; `460
    passed, 3 deselected`.
  - **Live end to end** (2026-10-11T05:58:49Z): Hermes 0.21.3 (provider key removed from its
    environment with `env -u openrouter_api_key`) -> `RelayServer` on 127.0.0.1 -> OpenRouter.
    Effective tools `['mcp__episalpha__echo_span']`; the model called it; final response `'Fourth
    quarter revenue was EUR 412.0 million.'`; relay summary `{"requests_used": 2, "usage":
    {"model_requests": 2, "prompt_tokens": 2862, "completion_tokens": 120, "cost_eur": null},
    "served_by": ["Nvidia", "Nvidia"], "failure": null}`. Two `model.call` spans in the JSONL;
    `model.call` spans visible in Phoenix project `episalpha-tests`.
  - Reasoning versus `max_tokens`: the relay records
    `llm.token_count.completion_details.reasoning`. The provider reports reasoning inside
    `completion_tokens` (M0-T04). With 120 completion tokens over 2 calls, the 4,000 cap was far
    from binding.
- Sample `model.call` lines (scripted provider; content keys appear only as `_bytes`/`_hash`):
  - success: `{"name": "model.call", "status": "UNSET", "attributes": {"openinference.span.kind": "LLM", "llm.model_name": "nvidia/nemotron-3-ultra-550b-a55b:free", "llm.provider": "openrouter.ai", "episalpha.request_index": 1, "episalpha.attempt": 1, "input.value_bytes": 241, "http.response.status_code": 200, "output.value_bytes": 352, "episalpha.outcome": "ok", "episalpha.served_by": "Nvidia", "llm.token_count.prompt": 11, "llm.token_count.completion": 7, "llm.token_count.total": 18, "llm.token_count.completion_details.reasoning": 3}}`
  - retry: `{"name": "model.call", "status": "ERROR", "status_message": "HTTP 503", "attributes": {"episalpha.request_index": 2, "episalpha.attempt": 1, "http.response.status_code": 503, "episalpha.outcome": "transient", ...}}`, followed by `{"episalpha.request_index": 3, "episalpha.attempt": 2, "http.response.status_code": 200, "episalpha.outcome": "ok", ...}`
  - budget exhausted: no upstream call, so no `model.call`; one `relay.refusal` span with
    `episalpha.error_code: BUDGET_EXCEEDED` (asserted in `test_refusals_are_logged_without_content`).
- Live requests this task: 2 (session total about 8 of the 40 approved).
- Outcome: PASS
