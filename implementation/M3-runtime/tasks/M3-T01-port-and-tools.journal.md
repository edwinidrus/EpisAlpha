# M3-T01 journal

## Attempt 1 — 2026-10-10 22:52 UTC to 2026-10-11 05:55 UTC — claude-opus-5-5
- Owner approval: live model requests (up to 40 for the unattended session) and public fetches,
  2026-10-10. Requests spent here: about 6 (see below).
- **MCP path proof (A5):**
  - Pinned Hermes: `git clone` of NousResearch/hermes-agent, checkout
    `c1488ac947c9bc33fd65ec464548dc9d8edd6122` -> `2026-09-20T20:49:54+05:30`, `version =
    "0.21.3"`. Installed editable with the `[mcp]` extra (`mcp 2.0.0`) in its own venv,
    `.episalpha/vendor/hermes-venv` (git-ignored), never in the application venv. The owner's
    personal `~/.hermes` install (0.20.6) was not touched.
  - Hermes' MCP client (`tools/mcp_tool_*`) tries the legacy `initialize` handshake first
    (offering `2025-11-25`), so a stdlib server suffices; no `mcp` dependency in EpisAlpha.
  - `scripts/probe_mcp.py`: stdlib newline-delimited JSON-RPC server, tool `echo_span`. Offline
    smoke test: initialize, tools/list, tools/call and server/discover (-32601) all as expected.
  - Registration without a model call: `register_mcp_servers({...})` ->
    `['mcp__episalpha__echo_span']`; `create_custom_toolset('episalpha', tools=names)` resolves
    to the same list. The probe server saw `initialize` (protocolVersion 2025-11-25),
    `notifications/initialized`, `tools/list`.
  - **Live turn 1** (2026-10-10T22:56:05Z, driver in the scratchpad, OpenRouter route,
    `max_iterations=3`): the effective tools sent to the model were
    `['tool_call', 'tool_describe', 'tool_search']`. Hermes' default `tools.tool_search.enabled:
    auto` deferred the MCP tool behind meta-tools. The model called `tool_search` twice and
    `tool_describe` once, hit the iteration cap and never called the tool. `api calls: 3`, plus
    one summary request.
  - Fix found in `model_tools.py` / `tools/tool_search.py`: config key
    `tools.tool_search.enabled: "off"`.
  - **Live turn 2** (2026-10-10T22:56:50Z, same driver, tool search off): effective tools
    `['mcp__episalpha__echo_span']`; the model called it with `{'span_id':
    'synthetic-span.revenue'}`; final response `'Fourth quarter revenue was EUR 412.0 million.'`
    (the exact quote); `api calls: 2`; the server saw `tools/call` with `name: echo_span`.
    **Proof PASSED.**
  - Recorded in `config/runtime.lock.json` -> `hermes.mcp_path_proof`. The tool prefix is
    `mcp__<server>__<tool>` (double underscores; M0-T03's `mcp_` note was wrong). M3-T03's
    harness must set `tools.tool_search.enabled: "off"`.
- Verify:
  - `grep -n "class SnapshotView\|def search\|def span\|class RuntimeContext\|def recompute"` ->
    `snapshots.py: class SnapshotView, def span, def search`; `research.py: class
    RuntimeContext`; `derivations.py: def recompute`.
  - **`SnapshotView` lacks claims, relations, instruments and market context**, which four tools
    need. Rather than widen the view silently, `ToolHost` takes them as explicit keyword inputs
    and filters each by the manifest (`permitted_claim_ids`, `permitted_relation_ids`,
    `instrument_ids`) or by the context's validated current-run IDs. `SnapshotView` is
    unchanged.
  - Baseline: four checks green, 399 passed.
  - Red first: `uv run pytest -q tests/runtime/test_tools.py` -> `ModuleNotFoundError: No module
    named 'episalpha.runtime'`.
- Did:
  - `src/episalpha/runtime/port.py`: `ResearchRuntimePort` (Protocol: `run_stage`, `cancel`),
    `ExitReason`, `ToolResult`. The candidate payload goes to the content-addressed
    `ObjectStore`; `StageResult.candidate_payload_hash` points at it, so the port needs no
    extra method.
  - `src/episalpha/runtime/tools.py`: `ToolHost` with the 8 tools (7 read-only plus
    `propose_skill`), `SkillProposal`, `TOOL_NAMES`. One envelope does budget, size cap,
    hashing and the `tool.<name>` span.
  - `src/episalpha/runtime/fake.py`: `FakeRuntime`, `Scenario` (7 scenarios). Payloads are
    labelled `fixture: true` plus `source`. `${RUN}` in fixtures becomes the run ID, matching
    host-assigned current-run IDs `<run_id>.<key>`.
  - `tests/fixtures/runtime/*.json` (7 scripts on the synthetic snapshot).
  - `src/episalpha/settings.py`: `Limits.max_skill_proposals = 2` and
    `max_skill_proposal_bytes = 4096` (global article 21: limits live in one place).
  - `tests/runtime/test_tools.py`: 27 tests.
  - `scripts/probe_mcp.py` (the disposable proof server).
- Decisions:
  - Market context excludes a close dated on the cutoff day (a midnight-UTC cutoff precedes that
    day's close). Marked `ponytail:` in the code.
  - With no series and the price source among `missing_sources`, the result is `SOURCE_FAILED`;
    otherwise `NO_DATA`.
  - An empty `get_numeric_facts` result is `NO_DATA`, not an empty success.
- Ran:
  - `uv run pytest -q tests/runtime` -> `27 passed`
  - Four checks: All checks passed; 50 files already formatted (after formatting
    `scripts/probe_mcp.py`); no issues in 27 source files; `426 passed, 3 deselected`.
- Sample spans (JSONL, long values shortened):
  - `{"name": "tool.search_evidence", "kind": "RETRIEVER", "attributes": {"openinference.span.kind": "RETRIEVER", "tool.name": "search_evidence", "tool.parameters_hash": "465197c37016873778256cb7c15da0b2952652d410c58d537f4b2a0a21693999", "tool.parameters_bytes": 28, "episalpha.args_hash": "465197c37016873778256cb7c15da0b2952652d410c58d537f4b2a0a21693999", "retrieval.documents.0.document.id_hash": "f1f99170231d96a73de327331ade828461e165334496b28ff1333de18ac8ab70", "retrieval.documents.0.document.id_bytes": 21, "retrieval.documents.0.document.content_hash": "aa147abb84b2d580602621415c8623204454d3fd62c7f9613fd1fcf4bb908874", "retrieval.documents.0.document.content_bytes": 55, "output.value_hash": "4650a02e42e05386c7c95cdf76b347dc8d821422a8f024a759dbdfb0a2a01d38", "output.value_bytes": 187, "episalpha.result_hash": "68fd8a8b8ccc090d6c3d4de87f834854e5d4b2ebe500042d938e34e4abb62542", "episalpha.bytes": 227, "episalpha.error_code": "", "outcome": "ok"}}`
  - `{"name": "tool.get_evidence_span", "kind": "TOOL", "attributes": {"openinference.span.kind": "TOOL", "tool.name": "get_evidence_span", "tool.parameters_hash": "22fb08e73658ba7bbb05d47d459d7fcd374110376d797a2439274df3f4437e19", "tool.parameters_bytes": 34, "episalpha.args_hash": "22fb08e73658ba7bbb05d47d459d7fcd374110376d797a2439274df3f4437e19", "output.value_hash": "eb49e42952ff6ec18d0679e04b413a678194159fa2bf72ad1e1e28a222de718a", "output.value_bytes": 90, "episalpha.result_hash": "02683f255c137b13df6e89f1d85310867e9f3a53d50e39b236a720dfadf6b28e", "episalpha.bytes": 143, "episalpha.error_code": "NOT_AUTHORIZED", "outcome": "ok"}}`
  - `{"name": "tool.compute_derivation", "kind": "TOOL", "attributes": {"openinference.span.kind": "TOOL", "tool.name": "compute_derivation", "tool.parameters_hash": "27282ce81376c8148cdce1b51b5a2faae060e332fb9232c11e4ee3a78b65979e", "tool.parameters_bytes": 119, "episalpha.args_hash": "27282ce81376c8148cdce1b51b5a2faae060e332fb9232c11e4ee3a78b65979e", "output.value_hash": "d212168d89b80df293dabfdc07b820f7f35faa3f28a168440be03c44d479959e", "output.value_bytes": 149, "episalpha.result_hash": "a30336ad67ca4fddaafc173ed6b1615d59e6bdc932815face627bb5666cc734a", "episalpha.bytes": 189, "episalpha.error_code": "", "outcome": "ok"}}`
- Outcome: PASS
