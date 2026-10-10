# Implementation progress

Task status, per-task verification and gate results moved to `implementation/` on 2026-10-10
(plan amendment A10), with rows migrated unchanged:

- Rollup and next task: [`implementation/STATUS.md`](../../implementation/STATUS.md)
- Per phase: `implementation/M<n>-<name>/PROGRESS.md` and `GATE.md`
- Session protocol: [`implementation/README.md`](../../implementation/README.md)

This file keeps the cross-cutting records below: owner inputs, findings, amendments and
repository notes.

## Owner inputs (plan section 1.4)

| Input | Status | Effect |
|---|---|---|
| Research model / provider / credential | **SUPERSEDED by A9** (see "Research route change" below) | Ollama, `glm-5.3`, `https://ollama.com/v1`, credential `ENV:ollama_api_key` from the git-ignored `.env`. Verified by live probe. Note: the id is `glm-5.3` on the cloud endpoint; `glm-5.3:cloud` is the local-daemon form. |
| Three demo companies + one theme | **RESOLVED** | Theme: company guidance and demand changes. LULU (CIK 0001397187) supported-thesis case; TSCO (0000916365) conflicting-evidence case; CALX (0001406666) insufficient-evidence case. CIKs verified against SEC `company_tickers.json`. **Case mapping is PROVISIONAL** — it reflects public reporting, not verified filing content, and M2-T04 must confirm or reassign it. |
| Price source and permitted local use | **RESOLVED and VERIFIED** | `alpha_vantage` `TIME_SERIES_DAILY`, credential `ENV:alpha_vantage_api_key`. Key supplied 2026-09-20 and confirmed live against LULU, TSCO and CALX (100 daily bars each, latest 2026-09-18). `sources.missing_credentials` is now empty. Two constraints found: the free tier refuses back-to-back calls (~1 req/sec) returning HTTP 200 with an `Information` key and no data, and `TIME_SERIES_DAILY_ADJUSTED` is premium so the free close is **unadjusted**. |
| Source scope | **RESOLVED (scope expansion)** | Owner chose the full TradingAgents shape: market, news, social, fundamentals, macro. This exceeds plan section 1.2's envelope of filings plus one price path. Each source now carries a `provenance` value (`primary`/`secondary`/`unverified`); the filings source must be `primary`, and social sources ship disabled. |
| Research route change (A9) | **DECIDED 2026-10-10, verification pending** | Owner chose OpenRouter `nvidia/nemotron-3-ultra-550b-a55b:free` (`ENV:openrouter_api_key`) as the research model. M0-T04 re-probes it live; until then the route is unverified. The `:free` data-logging policy is unconfirmed, and M0-T04 records the owner's acknowledgement. |
| Optional EUR spending limit | BLOCKED, not configurable | v0.1 has no cost reservation or verified pricing, so `limits.eur_cap` is rejected at load on purpose (plan section 3.8; acceptance row A22). |

## Findings that change later milestones

1. **The relay must not use `response_format`.** The endpoint accepts `json_schema` and
   `json_object` and **silently ignores both**, returning prose. Structured output comes from
   forced `tool_choice` arguments, validated host-side. M3-T02 must assert this rather than trust
   the advertised capability.
2. **The bounded repair in plan section 3.6 step 7 is load-bearing**, not defensive decoration.
3. `glm-5.3` is a reasoning model: trivial prompts cost 600-1600 completion tokens. The
   4 000-token per-call cap is workable but tight; re-measure at M3-T02.
4. **Hermes exact-pins its dependencies** and must never share the application virtualenv.
5. **An `unverified` source must never be the sole support for a material assertion.** Settings
   now expose `sources.unverified_source_ids`, but the validator does **not** enforce this yet.
   It must, before any social source is enabled. Tracked as the precondition on `reddit` and
   `stocktwits` shipping disabled.
6. **TradingAgents' `assets/schema.png` is older than their code.** The diagram shows Bloomberg,
   Reuters, EODHD and X; the current `dataflows` modules are Alpha Vantage, FRED, Yahoo Finance,
   SEC EDGAR, Reddit, StockTwits and Polymarket, plus `date_window.py` for point-in-time caching.

## Plan amendments (v1.1, 2026-09-20)

`EpisAlpha_MVP_Milestone_Implementation_Plan.md` was amended to v1.1 so later tasks build against
verified facts instead of assumptions. Section 0 of the plan carries the full record; in short:

| # | Change |
|---|---|
| A1 | Owner inputs 1.2/1.4 resolved: Ollama `glm-5.3`, LULU/TSCO/CALX, Alpha Vantage |
| A2 | Source set widened to the TradingAgents shape; `source_family` and `provenance_strength` added to the frozen vocabulary in 3.3; unverified-source rule added to 3.4 |
| A3 | 3.6 step 7 and M3-T02: the relay must not use `response_format` |
| A4 | 3.8: per-source daily budget and ≥1 s request spacing |
| A5 | 4.2, M0-T03, M3-T01: Hermes installs via Docker/installer/Nix or editable clone, never a built wheel; typed tools arrive over MCP |
| A6 | New 2.6: free-tier price close is unadjusted |
| A7 | 4.1: `tests/conftest.py` added to the target structure |
| A8 | (v1.2, 2026-10-10) Quantitative evidence layer, owner scope "Core numbers": new M1-T05 (derivation recomputation) and M2-T05 (point-in-time XBRL); M3-T01 gains `get_numeric_facts`/`compute_derivation`; numeric checks added to M4-T04, M5-T02, M6-T01. Returns, backtests, factor models deferred to 15.3. Reason: M1-T04 never recomputed derived values, and LLM financial arithmetic is unreliable |
| A9 | (v1.3) Research route moves to OpenRouter Nemotron 3 Ultra `:free`; new M0-T04 live re-probe; free-tier budget consequences recorded |
| A10 | (v1.3) Execution layer moves to `implementation/` (phase constitutions, plans, progress, gates, task packs) |
| A11 | (v1.3) Diagnose layer: M0-T05 `scripts/diagnose.py`, M0-T06 `observability.py`, M2-T06 connector events, event acceptance in M3+ |

The "Start here" section now points at M2-T01 rather than M0-T01.

## Repository note (not a task)

`EpisAlpha_Architecture_and_Implementation_Blueprint.md:Zone.Identifier` is tracked in commit
`8b7b4c6` and is **not** matched by the `.gitignore` pattern `*.Zone.Identifier`, because the
filename separator is `:` rather than `.`. **Resolved 2026-10-10:** file untracked with
`git rm --cached` (local copy kept) and the pattern changed to `*Zone.Identifier`.
