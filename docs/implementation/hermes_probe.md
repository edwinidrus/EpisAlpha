# M0-T03 — Hermes and model-route probe findings

**Probed:** 20 September 2026 · **Machine:** Linux/WSL, CPython 3.12.3, uv 0.11.7
**Machine-readable record:** `config/runtime.lock.json` · **Reproduce:** `uv run python scripts/probe_hermes.py config/demo.toml`

Everything below was observed. Where something was not observed it is stated as not observed
rather than assumed, per plan section 2.1.

## 1. Headline findings

1. **The selected model route works, and the model id is route-dependent.** On the direct cloud
   endpoint the id is `glm-5.3`. The `:cloud` suffix is the *local daemon's* convention for
   proxying the same model. The initial configuration paired `glm-5.3:cloud` with the cloud
   endpoint, which does not exist there; this was corrected in `config/demo.example.toml`.
2. **Provider-side structured output is advertised but silently ignored.** `response_format`
   with `json_schema` (`strict: true`) and with `json_object` both returned ordinary prose —
   in the second case markdown-fenced JSON that `json.loads` rejects. No error, no warning. This
   is precisely the OpenAI-compatibility subset risk the plan flagged (section 16, reference 12),
   and it is the dangerous shape of it: silent, not a failure.
3. **Forced tool calls do deliver reliable structured output.** With
   `tool_choice` pinned to a named function, the route honoured the choice and returned arguments
   that parse as JSON and satisfy a nested array-of-objects schema. Usage is reported.
4. **Hermes cannot be handed a Python callable as a tool.** `toolsets.create_custom_toolset`
   composes *existing tool names*; `AIAgent.__init__` has no tool-registration parameter.
   EpisAlpha's typed tools must therefore reach Hermes over MCP, as an external server Hermes
   connects to as a client.

## 2. Model route

| Property | Observed |
|---|---|
| Endpoint | `https://ollama.com/v1` (OpenAI chat-completions shape) |
| Model | `glm-5.3` |
| Credential | `ENV:ollama_api_key`, resolved from the git-ignored `.env` |
| Tool calls | yes |
| Forced `tool_choice` | honoured; `finish_reason: tool_calls` |
| Nested tool schema | respected (array of objects with enums) |
| `response_format: json_schema` | **ignored** |
| `response_format: json_object` | **ignored** (fenced output) |
| Usage reported | yes — `prompt_tokens`, `completion_tokens`, `total_tokens` |
| Pricing | none in the payload — cost stays unknown (row A22) |

`glm-5.3` is a reasoning model. Trivial prompts consumed 600–1600 completion tokens, so the
4 000-token per-call cap from plan section 3.8 is workable but tight; re-measure at M3-T02.

## 3. Hermes upstream

Official repository `NousResearch/hermes-agent` (MIT), not a mirror. Inspected commit
`c1488ac947c9bc33fd65ec464548dc9d8edd6122` (2026-09-20), repository version `0.21.3`,
`requires-python = ">=3.11,<3.14"` — compatible with this project's 3.12.

**Install finding (owner approved the git install).** A `git+https` wheel build is **refused by
upstream**, deliberately:

```
RuntimeError: Building wheels or sdists for hermes-agent is not supported.
Hermes is distributed via the shell installer, Docker image, or Nix.
```

The supported paths are the shell installer, Docker, Nix, or an editable install from a clone.
Cloning at `c1488ac` and running `uv pip install -e .` into an isolated virtualenv **succeeded**,
and every API fact below was read from `0.21.3` itself, not inferred from the older PyPI `0.19.0`.
PyPI still lags at `0.19.0`.

**Consequence for M3:** the runtime should use the **Docker image**. It is upstream's supported
distribution and it already satisfies the isolation plan section 4.2 requires — `runtime/Dockerfile`
and `runtime/compose.yaml` are in the plan's target structure for exactly this reason. Hermes
exact-pins its dependencies and must never share the application environment.

### Controls available on `run_agent.AIAgent`

| Plan requirement | Available as |
|---|---|
| Tool allowlist | `enabled_toolsets` / `disabled_toolsets` |
| Fresh profile | `skip_context_files`, `skip_memory`, `load_soul_identity`, `session_id` |
| Budget | `max_iterations`, `iteration_budget`, `max_tokens` |
| Cancellation | `interrupt()`, `clear_interrupt()`, `close()` |
| Trace | `event_callback`, `tool_start_callback`, `tool_complete_callback`, `step_callback`, `save_trajectories` |
| Usage | `get_activity_summary()`, `get_credits_spent_micros()`, `get_credits_state()` |
| Main / auxiliary routing | `base_url`, `api_key`, `provider`, `api_mode`, `model`, `switch_model()` |

`fallback_model`, `providers_allowed`, `providers_ignored`, `providers_order` exist and **must be
left unset** — plan section 1.2 forbids automatic provider substitution.

All of the above were confirmed on the pinned `0.21.3`, not only on `0.19.0`.

### The tool-injection path

`AIAgent.__init__` exposes **none** of `mcp_servers`, `tools`, `extra_tools`, `custom_tools` or
`tool_registry`, and `create_custom_toolset(name, description, tools, includes)` composes existing
tool *names*. MCP servers are configured by file (`mcp.json` under `$HERMES_HOME` / `~/.hermes`)
and their tools surface with an `mcp_` name prefix, which `create_custom_toolset` can then
allowlist. So the M3 design is:

```text
EpisAlpha MCP server  ->  mcp.json  ->  tools appear as mcp_*
                      ->  create_custom_toolset("episalpha", tools=["mcp_..."])
                      ->  enabled_toolsets=["episalpha"]
```

This is evidence-backed but **not yet proven end to end**. M3-T01/M3-T03 must demonstrate it with
a working probe before the runtime is built on it.

### Not observed

- **Custom typed tools in-process.** No registration API for a callable (see finding 4).
- **An end-to-end agent turn using an EpisAlpha tool.** Not attempted: M0-T03 stops before
  building a runtime, and this depends on the MCP decision below.

## 4. Consequences for the architecture

1. **The relay must not depend on `response_format`.** Structured output comes from forced
   tool-call arguments, validated host-side. M3-T02 must assert this rather than trusting the
   provider's advertised capability.
2. **The bounded repair in plan section 3.6 step 7 is load-bearing**, not defensive decoration.
3. **M3-T01/M3-T03 carry a real design decision:** EpisAlpha's snapshot-bound typed tools are
   exposed to Hermes as an external MCP server. This must be resolved with a working probe before
   the runtime is built around it, not assumed.
4. **Hermes stays in its own environment or container.**

## 5. Gate G0 status

- Offline portion: passing (see `progress.md`).
- Model route: **verified**.
- Hermes tool-injection path: **open** — the in-process route is ruled out; the MCP route is
  unproven. G0 is not declared passed on this evidence, and no `FakeRuntime` result substitutes
  for it.


## 6. Data sources (owner decision, 2026-09-20)

The source set follows the TradingAgents reference architecture. Note the published
`assets/schema.png` is **older than their code**: the diagram shows Yahoo Finance, X, Reddit,
EODHD, Bloomberg, FinHub and Reuters, while the current `tradingagents/dataflows` modules are
Alpha Vantage (stock, fundamentals, indicator, news), FRED, Yahoo Finance, **SEC EDGAR**, Reddit,
StockTwits and Polymarket, plus `date_window.py` for point-in-time caching. SEC EDGAR appears in
both their set and EpisAlpha's plan, so the filings choice was already aligned.

The owner chose the **full TradingAgents shape** (market, news, social, fundamentals, macro),
which exceeds plan section 1.2's v0.1 envelope of filings plus one price path.

Because that set mixes filings with forum posts, each source carries a `provenance` value. It is
not a quality score — it records what *kind* of thing the source is:

| Provenance | Meaning | Sources |
|---|---|---|
| `primary` | the issuer's or regulator's own document | `sec_edgar`, `alpha_vantage`, `fred` |
| `secondary` | a report *about* a primary source | `alpha_vantage_news` |
| `unverified` | public commentary, no availability guarantee, no accountable publisher | `reddit`, `stocktwits` |

Settings enforce that the filings source must be `primary`. Social sources ship **disabled**:
they cannot establish that anything is true, and they should stay off until the validator
enforces that an `unverified` source is never the sole support for a material assertion. That
rule is not implemented yet.

**Price source:** `alpha_vantage`, free tier 25 requests/day and 5/minute — ample for three
tickers with caching, and the connector must cache rather than re-fetch. Credential reference
`ENV:alpha_vantage_api_key`; **the key has not been issued yet**, and settings report that through
`sources.missing_credentials` without failing the load.

## 7. Demo corpus (owner decision, 2026-09-20)

Theme: **company guidance and demand changes**. CIKs verified against SEC `company_tickers.json`.

| Ticker | CIK | Intended case | Basis |
|---|---|---|---|
| LULU | 0001397187 | supported thesis | Cut full-year guidance after a Q2 revenue decline; Americas demand weakness; guidance moved to a 5-7% revenue decline |
| TSCO | 0000916365 | conflicting evidence | Cut adjusted EPS guidance to $1.90-2.00 from $2.13-2.23 and sales growth to 2.5-3.5% from 4-6%, attributed to both demand and costs, while growth stayed positive |
| CALX | 0001406666 | insufficient evidence | Small-cap filer expected to leave the guidance question unanswerable |

**The case mapping is PROVISIONAL.** These are intentions drawn from public reporting, not
verified properties of the filings themselves. M2-T04 curates the corpus and must confirm or
reassign them — particularly CALX, where "insufficient evidence" is a hypothesis about what the
filings do *not* contain.

## 8. Route change (A9), probed 2026-10-10 by M0-T04

The research route moved from Ollama `glm-5.3` (section 2, kept as history in
`config/runtime.lock.json` → `model_route_history`) to OpenRouter
`nvidia/nemotron-3-ultra-550b-a55b:free`. The owner approved the live calls and acknowledged the
unconfirmed `:free` data-logging policy on 2026-10-11 (local time). Probe prompts were synthetic.

**Public listing** (`GET /api/v1/models`, no key, 2026-10-10): context 1,000,000 tokens, max
completion 65,536, pricing 0/0, `supported_parameters` = `include_reasoning`, `max_tokens`,
`reasoning`, `reasoning_effort`, `seed`, `temperature`, `tool_choice`, `tools`, `top_p`.
`response_format` is **not** listed for `:free` (the paid variant lists it). The endpoints
listing shows one provider: Nvidia.

**Probe** (`uv run python scripts/probe_hermes.py config/demo.toml`, 2026-10-10T22:18:33Z, exit 0):

| Observation | Result |
|---|---|
| Forced `tool_choice` honoured | yes, `finish_reason: tool_calls` |
| Arguments parse as JSON | yes, keys `assertions`, `stance` |
| `provider.allow_fallbacks: false` | accepted (HTTP 200) |
| Served by | `Nvidia` (response `provider` field) |
| Usage reported | yes: prompt 411, completion 213, of which reasoning 122; `cost: 0` |
| `response_format` (json_schema) | content parsed as JSON with the requested keys |

**Live tests** (`uv run pytest -q -m live tests/integration/test_hermes_probe.py`,
2026-10-10T22:19:18Z): `2 passed in 11.36s`.

**Reading the results.**
- Structured output via forced tool choice works on this route. The relay design (A3) is
  unchanged.
- The `response_format` result differs from glm-5.3, which returned prose. One call is weak
  evidence: the parameter is not listed for `:free`, so the JSON may come from the model
  following the prompt rather than the provider enforcing the schema. The relay stays
  tool_choice-only regardless.
- Reasoning tokens are reported inside `completion_tokens`. Whether `max_tokens` caps reasoning
  was not probed directly.
- `usage.cost` is present and 0 (OpenRouter credits, not EUR). `cost_eur` stays `None` in v0.1.

**Limits re-check.**
- `max_output_tokens_per_call = 4000`: a trivial forced tool call used 213 completion tokens
  (glm-5.3 used 600–1,600). 4,000 is comfortable here; re-measure on real stage prompts at M3-T02.
- `max_model_requests = 8` per run at 50 requests/day gives at most 6 runs/day. Enough for M3
  and M4, not for the M6 campaign (owner decision at M6).
- No 429 was seen. Free-tier limits remain unprobed (`OpenRouter blog 2026`).
