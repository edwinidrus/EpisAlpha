# M3-T03 journal

## Attempt 1 — 2026-10-11 06:00–06:15 UTC — claude-opus-5-5
- Owner approval: up to 40 live requests for the unattended session (2026-10-10). Requests left
  before this task: about 31.
- Verify:
  - **Learning keys at the pin** (grep plus `DEFAULT_CONFIG` introspection in the Hermes venv):
    `memory.memory_enabled: True`, `memory.user_profile_enabled: True`,
    `auxiliary.background_review.enabled: True`, `curator.enabled: True`,
    `skills.write_approval: False`, `tools.tool_search.enabled: auto`. All found, none
    renamed; all default to on. The worker overrides every one (`write_approval: true`).
    `skill_manage` exists as a tool and is excluded by the toolset allowlist.
  - Controls: `AIAgent.__init__` at c1488ac has `enabled_toolsets`, `skip_memory`,
    `skip_context_files`, `load_soul_identity`, `skip_background_review`, `session_id`,
    `max_iterations`, `max_tokens`, `request_overrides`, `tool_complete_callback`,
    `fallback_model` (left unset) and `providers_*` (unset). `interrupt()` lives in
    `agent/interrupt_control.py`.
  - **Architecture constraint:** the app venv cannot import Hermes (exact pins). So
    `runtime/hermes.py` is the host adapter and never imports Hermes; `worker/hermes_stage.py`
    runs with Hermes' interpreter, and the tools reach it over the host MCP HTTP server
    (M3-T02b, split out of this task).
  - Hermes makes one extra tool-less "summary" request when the iteration budget runs out
    (`agent/turn_finalizer.py:157`), but not when interrupted. The worker interrupts after the
    submit tool returns and disables the summary fallback.
  - **`tool_choice: "required"` probe** (1 request): `finish_reason: stop`, a pseudo tool call
    in the text. **Not honoured.** Design changed: the relay's `StagePolicy` caps each stage's
    requests and forces the named submit tool on its last one (named forcing verified in
    M0-T04). New limits: `max_researcher_requests 4`, `max_critic_requests 2`,
    `max_synthesizer_requests 1` (7 of 8; 1 left for M4's bounded repair).
- Did: `worker/hermes_stage.py`, `src/episalpha/runtime/hermes.py` (`Harness`,
  `load_harness`, `skill_set_hash`, `read_worker_json`, `HermesRuntime`, `StageReport`),
  `harnesses/baseline/{researcher,critic,synthesizer,contradiction_search}.md` and
  `config.json`, `tests/runtime/test_hermes_adapter.py` (with
  `tests/fixtures/runtime/fake_worker.py`), `tests/integration/test_hermes_runtime.py` (live);
  small hooks in `observability.py` (`TraceHandle`, `capture`, `restore`),
  `model_relay.py` (`StagePolicy`, `trace`), `mcp_server.py` (`trace`), `tools.py`
  (`result_hashes`), `settings.py` (stage caps).
- Red first: **not honoured this time**. `hermes.py` was written before
  `test_hermes_adapter.py`. The tests were then written against the pack's list and passed
  (12 passed).
- **Live run 1** (2026-10-11T06:13:16Z): researcher completed (4 requests: 3 searches, then the
  forced submit on the 4th); critic completed (2); synthesizer submitted (1, forced) but was
  rejected: `invalid_output: assertions.1: Value error, every assertion must reference a claim
  or a hypothesis`. The host refused the malformed output as designed. 7 requests.
  - Root causes:
    1. `search_evidence` did whole-phrase substring matching. The model's natural queries
       ("weaker demand", ...) found nothing, so the critic wrote "no evidence about demand"
       although the snapshot has a demand span (searches in Phoenix: 4 of 5 returned 0 hits).
    2. The synthesizer cited `"k1], "` (a corrupted ID) and the critic's local key `k1`, which
       my live brief never turned into a canonical ID.
  - Also found: `state.db` in `HERMES_HOME`. Traced with a stub (zero model cost): pinned
    Hermes creates it on `import run_agent`; `_session_db` stays `None`; tables `sessions` and
    `messages` hold 0 rows. The host now counts rows (read-only) and flags `state.db` only when
    it holds data (test added).
- Fixes (attempt 2 of 2 on this issue):
  - `ToolHost.search_evidence`: deterministic keyword scoring (distinct query words of 3+
    characters, minus stopwords; ties in document order), marked `ponytail:`. Two M3-T01 tests
    searched the single letter `"e"`, which is no longer a searchable word; their queries changed
    to `"quarter demand"` with the same assertions. Test added for phrase queries.
  - `synthesizer.md`: copy IDs exactly, one per item; uncited points go to
    `missing_information`.
  - Live brief: the critic's counter-claims become canonical `<run>.<key>` records (M4-T01
    does this for real).
- **Live run 2** (2026-10-11T06:17:27Z): `1 passed in 64.18s`.
  - run `run.live-809c4094`, trace `279e56da2fd6b7436795661d00283c7b`
  - harness hash `de8654323245a7132ae0401643b77c19747eb06b209547e252df0ea467a45610`; skill-set
    hash = the empty set (`sha256("[]")`)
  - served_by: Nvidia for all 6 calls; usage 6 requests, prompt 24,669, completion 1,706
    tokens, `cost_eur: None`
  - researcher: completed, 3 requests, tools `search_evidence, get_evidence_span x2,
    submit_research` (submitted early; the interrupt stopped the turn), 23.7 s. Claims c1
    (`synthetic-span.revenue`) and c2 (`synthetic-span.demand`), both real snapshot spans.
  - critic: completed, 2 requests, 2 searches, 10.3 s, no contradictions found.
  - synthesizer: completed, 1 forced request, 29.4 s, stance `investigate`, 5 assertions
    (observation, interpretation, expectation, variant_view, invalidation), all referencing
    `run.live-809c4094.c1`/`c2`.
  - Effective tools equalled the allowlist in every stage; `learning_writes: []`;
    `fallback_model: None`; relay requests (6) = the sum of stage requests (no hidden calls).
  - Phoenix: 21 spans in one trace (`research.run`, 3 `stage.*` AGENT, 6 `model.call` LLM, 5
    TOOL, 3 RETRIEVER, 3 `relay.refusal` = Hermes' `POST /api/show` probe per stage). Prompts
    present in Phoenix; the JSONL `model.call` lines hold `input.value_hash` only.
- Four checks: All checks passed; 60 files formatted; no issues in 31 source files; `497
  passed, 4 deselected`.
- Live requests this task: 14 (1 probe, 7, 6). Session total about 22 of 40.
- Outcome: PASS
