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
| Research route change (A9) | **DECIDED 2026-10-10, VERIFIED 2026-10-10 (M0-T04)** | Owner chose OpenRouter `nvidia/nemotron-3-ultra-550b-a55b:free` (`ENV:openrouter_api_key`) as the research model. Owner approved the M0-T04 live calls and acknowledged the unconfirmed `:free` data-logging policy on 2026-10-11. Live probe: forced `tool_choice` honoured, served by Nvidia, `allow_fallbacks: false` accepted; live tests 2 passed. |
| Diagnose service content policy (A14) | **DECIDED 2026-10-10** | Local Arize Phoenix receives full content (prompts, completions, tool I/O, validation detail); JSONL fallback receives metadata only; secrets redacted before any exporter; Phoenix bound to 127.0.0.1, bounded retention. Tracing foundation built before M3 (M0-T06/T07). |
| Unattended overnight build (2026-10-10/11) | **APPROVED 2026-10-10 ~22:30 UTC** | Owner asked for the whole implementation to be built unattended, complying with the constitutions and gates, with one Markdown report per phase. Approved for that session: (1) up to **40 live model requests** on the OpenRouter route (M3/M4 live checks; public SEC excerpts may be sent); (2) pulling and running **digest-pinned Docker images** (Phoenix, Hermes) bound to 127.0.0.1 or an internal network; (3) M3-T04 hardens the **current rootful Docker** (rootless/userns-remap stays an owner TODO, G3 isolation item partial); (4) **public data GETs** from SEC EDGAR and Alpha Vantage within their rate limits. Owner-only items (walkthroughs, G2 inspection checkpoint, M6 capacity decision) stay open. |
| Proceed past G4 PARTIAL (2026-10-11) | **DECIDED 2026-10-11 ~07:15 UTC** | After the M4 report, the owner committed manually and said "please proceed the further milestones". M5-T01 was built on G4's offline pass; the M4-T04 real-case reviews stay BLOCKED on the G2 checkpoint. |
| Move to another environment (2026-10-11) | **DECIDED 2026-10-11 ~07:40 UTC** | Owner: "please stop, and please make Handoff MD and orchestration all with docker, and please make commit then push to github". Development stopped after M5-T01; `HANDOFF.md`, `Dockerfile`, `compose.yaml`, `compose.live.yaml` and `scripts/setup_worker.py` added; commit and push to `origin` authorised by that message. |
| Proceed past G5 PARTIAL, unattended (2026-10-12) | **DECIDED 2026-10-12 ~20:40 UTC** | Owner: "please make it full auto and running over the night, so i can sleep … make a git pull". Read as: continue the milestones past G5's open manual checks, as with G4. Limits the session keeps because the message does not lift them: **no live model requests** (none approved for this session), **no commits or pushes**, owner-only checkpoints (G5 Obsidian check, M6 label review, M6 capacity decision) stay open and tasks needing them stop at DONE_OFFLINE. |
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
| A12 | (v1.4) Runtime hardening: relay field allowlist, digest-pinned non-root read-only worker, DNS exfiltration blocked, symlink-safe output reading, rootless Docker recommended, Hermes native learning off at runtime |
| A13 | (v1.4) Safe continuous learning: `propose_skill` hook in M3/M4, new milestone M8 (screen → evaluate → owner approves → read-only use, revocable) |
| A14 | (v1.5) Whole-system Diagnose service: OpenTelemetry spans for every boundary, JSONL fallback, local Arize Phoenix (M0-T06 rewritten, M0-T07 new), trace-grounded improvement backlog (M8-T05) |

The "Start here" section now points at M2-T01 rather than M0-T01.

### A15 — Portable Docker orchestration (owner approved 2026-10-11)

- **Decision:** the full stack, live Hermes runs included, runs from `git clone` +
  `docker compose build` on Linux, macOS and Windows. Distribution by local build only.
  Approach A (Docker-native).
- **Design:** `docs/superpowers/specs/2026-10-11-portable-docker-design.md`.
  **Plan:** `docs/superpowers/plans/2026-10-11-portable-docker.md`.
- **Changes approved with it:**
  1. The app and Phoenix share one network namespace (anchor `net`). Phoenix leaves its own
     network but stays loopback-only from the host.
  2. In the `compose` sandbox topology, the relay and MCP server listen inside that namespace
     (reachable on `episalpha-app` only, token-protected) instead of on the `docker0` gateway.
  3. Docker Engine >= 26 (API 1.45) is required.
  4. M5 constitution article 9 now reads "reachable from the host's loopback only".
  5. A one-shot `init` service prepares the bind-mount directories (rootful engines create them as root).
- **Tasks:**
  - M0-T08: portable offline stack;
  - M3-T05: `compose` sandbox topology and live check. This reopens G3.
- **Owner checks outstanding:** macOS Apple Silicon and Windows Docker Desktop. Run build →
  check → up → fake run → live run, and confirm the `DOCKER_GID=0` socket access and the arm64
  Hermes build.
- **Findings:**
  - A runtime-assembly failure after admission (e.g. a relay bind error) strands the run in QUEUED holding the job slot; preflight catches the common causes before admission. Recover with `research recover`. Not fixed in A15.
  - **Fixed 2026-10-12** (deferred minors from the A15 reviews, each verified; red test first where code changed):
    - Preflight's Docker queries had no timeout, and preflight runs on the submit path: a hung Docker daemon froze the UI submit. Preflight now uses `sandbox._probe` (15 s, then refused as "engine unreachable"); `_docker` stays unbounded because it also runs `docker build` and `docker stop` (a first attempt put the timeout on `_docker` and would have killed image builds; caught in self-review). Tests: `test_a_hung_docker_engine_is_refused_not_waited_on`, `test_builds_and_stops_are_not_cut_short_by_the_probe_timeout`.
    - `scripts/diagnose.py` compared each run with the previous line from *any* environment. The container skips the 8 compose-config tests, so the documented `docker compose … run --rm check` reported `FAIL … regressions 1` (`passed 637 -> 630`) after any host run. Lines now carry `environment` (`host`/`container`; untagged = host) and compare like with like (`test_the_baseline_is_the_last_line_from_the_same_environment`). Container and host both PASS afterwards.
    - `compose.dev.yaml` `check`: `cap_drop: [ALL]`, `no-new-privileges`; verified by a full container `check` run.
    - `.gitattributes`: `*.sql text eol=lf` (the two migrations).
  - **Fixed 2026-10-12, CI:** the starter `Pylint` workflow (added on GitHub 2026-10-11) ran on Python 3.8–3.10 and could not parse this 3.12 code (`E0001 … invalid syntax`, reproduced locally); it failed on every push. Replaced by `.github/workflows/checks.yml`: the four standard checks with uv 0.11.6 and Python 3.12, no secrets. Verified on a clean copy of the tracked files (no `.env`, no `.episalpha`): four checks green, `637 passed`. Not yet seen running on GitHub (needs a push).

## Repository note (not a task)

`EpisAlpha_Architecture_and_Implementation_Blueprint.md:Zone.Identifier` is tracked in commit
`8b7b4c6` and is **not** matched by the `.gitignore` pattern `*.Zone.Identifier`, because the
filename separator is `:` rather than `.`. **Resolved 2026-10-10:** file untracked with
`git rm --cached` (local copy kept) and the pattern changed to `*Zone.Identifier`.

## v0.1 handoff (M7-T03, 2026-10-13)

**State.** Every buildable v0.1 task is DONE or DONE_OFFLINE; M4-T04 and M7-T03 are BLOCKED on
the owner. Gates: G0–G3 PASSED; G4, G5, G6, G7 PARTIAL (offline criteria pass; owner and live
parts open). Default suite 731 passed, offline, no credentials; `scripts/demo_smoke.py` passes
from a clean copy in 4.7 s. Evidence: `docs/implementation/demo_acceptance.md`, each phase
`GATE.md`, `implementation/DIAGNOSTICS.md`, `implementation/logs/diagnose.jsonl` (40 full runs,
324 -> 731 tests).

**Owner actions that unblock the rest, in order.**
1. G5: open the exported vault in Obsidian; count your own clicks from an assertion to its passage.
2. G2 checkpoint: live ingestion of the three cases' filings plus hand inspection (unblocks
   M4-T04 and real evidence for M6).
3. M6: review and sign the development label drafts; author 8 more development, 6 validation and
   6 final-check cases with their sealed labels; decide free-tier capacity
   (`limits.campaign_requests_per_day`); approve the live campaign's requests.
4. M7-T03: be present for the live walkthrough (real run, live campaign report, intentional
   source and model failures, browser refresh).

**Next eligible work after v0.1 — named, not started (M7 article 6).**
1. Forward forecast logging.
2. The optional paper/evaluation lab.
3. The A8 follow-ons in plan section 15.3: event-window reaction, factor baselines, Deflated
   Sharpe and PBO.
4. M8 learning loop (post-v0.1, after G7).
