# M3-T02b journal

## Attempt 1 — 2026-10-11 06:05 UTC — claude-opus-5-5
- Origin: split out of M3-T03 (global article 19). M3-T03 needed an MCP HTTP server, candidate
  schemas, the host adapter, the worker and the harness, which is more than one pack's 1–3
  files.
- Why HTTP: Hermes exact-pins its dependencies and must never share the application venv, so
  the app cannot import it. The worker runs in Hermes' own environment, where the snapshot does
  not exist, so the tools stay on the host behind an MCP Streamable HTTP endpoint.
- Verify:
  - Baseline: four checks green, 460 passed.
  - Red first: `ModuleNotFoundError: No module named 'episalpha.runtime.candidates'`.
  - Fixture fix found while designing: the fake fixtures used `"section": "counter_case"`,
    which is not a `ThesisSection` (valid values: observation, interpretation, expectation,
    variant_view, transmission, bull_case, bear_case, invalidation). Changed to `bear_case`.
- Did:
  - `src/episalpha/runtime/candidates.py`: `ResearchCandidate`, `CritiqueCandidate`,
    `ThesisCandidate` (strict, decimal strings, local keys `^[a-z][a-z0-9_-]{0,15}$`, unique
    keys, reported claims cite spans, derived claims name a derivation, no `hypothesized`
    claims), `parse_candidate` (strips fake provenance keys), `submit_schema` (inlined, no
    `$ref`, decimals as strings), `SUBMIT_TOOLS`.
  - `src/episalpha/runtime/mcp_server.py`: `handle_rpc` (initialize with a handshake-version
    echo, ping, tools/list, tools/call, -32601 otherwise), `stage_tools` (per-stage tool lists,
    argument type and unknown-key checks, first-submission-wins submit tool with a
    `tool.submit_<stage>` span), `McpToolServer` (stdlib, `/mcp`, bearer token -> 401, 413 over
    256 KiB, 202 for notifications, 405 for GET and DELETE, JSON-RPC batches).
  - `tests/runtime/test_mcp_server.py`: 21 tests.
- Ran:
  - `uv run pytest -q tests/runtime/test_mcp_server.py` -> `21 passed`
  - Hermes registration with no model call: pinned Hermes 0.21.3 with
    `{'url': 'http://127.0.0.1:18791/mcp', 'headers': {'Authorization': 'Bearer ...'}}` ->
    `['mcp__episalpha__compute_derivation', 'mcp__episalpha__get_evidence_span',
    'mcp__episalpha__get_market_context', 'mcp__episalpha__get_numeric_facts',
    'mcp__episalpha__get_support_and_contradictions', 'mcp__episalpha__propose_skill',
    'mcp__episalpha__resolve_instrument', 'mcp__episalpha__search_evidence',
    'mcp__episalpha__submit_research']`
  - Four checks: All checks passed; formatted; no issues in 30 source files; `481 passed`.
- Outcome: PASS
