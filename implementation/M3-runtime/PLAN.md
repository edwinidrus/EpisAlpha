# M3 plan: bounded Hermes runtime

**Goal:** real Hermes produces traceable candidate outputs, while canonical evidence and
evaluation stay outside its authority.

**Plan source:** plan §9 (M3-T01..T04), §3.6–3.8, §4.2; amendments A3, A5, A8, A9, A11.

## Tasks

| Task | Title | Status | Depends on | Pack |
|---|---|---|---|---|
| M3-T01 | Runtime port, fake runtime, typed tools | DONE | G2, M2-T05, M2-T06 | [pack](tasks/M3-T01-port-and-tools.md) |
| M3-T02 | Single-route model relay | DONE | M3-T01, M0-T04 | [pack](tasks/M3-T02-model-relay.md) |
| M3-T02b | MCP tool server and stage candidate schemas (split from M3-T03) | DONE | M3-T02 | [pack](tasks/M3-T02b-mcp-server.md) |
| M3-T03 | Hermes adapter and frozen research harness | DONE | M3-T02b | [pack](tasks/M3-T03-hermes-adapter.md) |
| M3-T04 | Whole-worker isolation and watchdog | DONE | M3-T03 | [pack](tasks/M3-T04-isolation.md) |

## Architecture slice

```text
host (trusted)                                   container (untrusted)
┌─────────────────────────────────┐              ┌──────────────────────────────┐
│ runner (M4) ─ RuntimeContext     │  run_stage   │ Hermes AIAgent (pinned)      │
│ runtime/port.py  ResearchRuntime │─────────────▶│  enabled_toolsets=[episalpha]│
│ runtime/tools.py typed tools ◀───┼── MCP ───────│  mcp_* tools only            │
│ runtime/model_relay.py ◀─────────┼── HTTP ──────│  base_url = relay, run token │
│   └─▶ OpenRouter (key held here) │              │ mounts: snapshot RO, out RW  │
└─────────────────────────────────┘              └──────────────────────────────┘
```

## Route facts that matter here (M0-T04 records the observed values; use those, not these)

- Endpoint `https://openrouter.ai/api/v1/chat/completions`, model
  `nvidia/nemotron-3-ultra-550b-a55b:free`.
- `tools` and `tool_choice` are listed. `response_format` is not listed for `:free`, and is never
  used anyway (A3).
- Max completion is 65,536 tokens; `Settings.limits.max_output_tokens_per_call` (4,000) is the
  binding cap. `reasoning` / `reasoning_effort` exist. Whether reasoning tokens count toward
  `max_tokens` must come from M0-T04 observation.
- Free tier: 20 requests/min; 50/day, or 1,000/day with at least $10 of lifetime credits. At 8
  requests per run that is at most 6 live runs/day. Plan live tests accordingly.

## Open questions (resolve inside the named task, recording evidence)

1. **MCP server dependency (M3-T01).** Exposing tools over MCP probably needs the `mcp` Python
   SDK, or a minimal stdio JSON-RPC server written with the stdlib. Prefer the stdlib if the
   protocol subset is small. Adding `mcp` needs owner approval (global constitution article 24).
2. **Which HTTP endpoints does pinned Hermes call (M3-T02)?** The relay implements only those,
   with no invented OpenAI compatibility.
3. **HTTP client for the relay (M3-T02).** `httpx` is in the plan's allowed set but is **not
   installed** (`pyproject.toml` lists only pydantic and typer). Use stdlib `urllib`, as
   `scripts/probe_hermes.py` does, unless streaming or connection control needs `httpx`.
   Record that choice in the M3-T02 journal.
4. **Docker availability on this WSL host (M3-T04).** If it is absent, M3-T04's live boundary
   test is BLOCKED, and that is reported as such.
