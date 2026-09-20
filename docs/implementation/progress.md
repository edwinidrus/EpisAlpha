# Implementation progress

One row per task card (plan section 2.4). A task is DONE only when its acceptance checks actually
pass, with the real command output recorded. Commits remain an explicit owner action.

| Task | Status | Changes | Verification | Blocker | Next |
|---|---|---|---|---|---|
| M0-T01 | DONE | `pyproject.toml`, `src/episalpha/__init__.py`, `src/episalpha/cli.py`, `tests/integration/test_package.py`, `.gitignore`, `uv.lock` — Python package with an `episalpha` console entry point, `--version`, registered `live` marker, lint/type/test configuration. | 2026-09-20: `uv sync --all-groups` → editable install OK; `uv run episalpha --version` → `0.1.0`; `uv run ruff check .` → All checks passed; `uv run ruff format --check .` → 3 files already formatted; `uv run mypy src/episalpha` → Success: no issues found in 2 source files; `uv run pytest -q -m "not live"` → 2 passed | None | M0-T02 |
| M0-T02 | DONE | `src/episalpha/settings.py`, `config/demo.example.toml`, `tests/contracts/test_settings.py`, `README.md`, `pyproject.toml`/`uv.lock` (+`pydantic>=2.11`) — one validated settings object holding paths, provider route, demo selection, source IDs and every plan section 3.8 limit; stdlib `tomllib`; credentials are `ENV:NAME` references resolved lazily. | 2026-09-20: four standard checks pass; `uv run pytest -q tests/contracts/test_settings.py` → 31 passed | None for offline work | M0-T03 |
| M0-T03 | DONE | `scripts/probe_hermes.py`, `config/runtime.lock.json`, `docs/implementation/hermes_probe.md`, `tests/integration/test_hermes_probe.py` (`live`); corrected `config/demo.example.toml`. Probed the real route; inspected Hermes's API surface **at the pinned commit `c1488ac` / 0.21.3** after the owner approved the git install. | 2026-09-20: `uv run python scripts/probe_hermes.py config/demo.toml` → real calls to `glm-5.3`; `uv run pytest -q -m live tests/integration/test_hermes_probe.py` → 2 passed in 16.93s | Hermes MCP tool path identified but unproven end to end (M3) | M1-T01 |
| M1-T01 | DONE | `src/episalpha/contracts/knowledge.py`, `tests/fixtures/synthetic_knowledge.py`, `tests/contracts/test_knowledge.py`, `tests/conftest.py` — Entity, Instrument, EvidenceDocument, EvidenceSpan, Claim, NumericFact, Derivation, Event, Hypothesis, Relation, SemanticAssessment; frozen vocabularies; `ALLOWED_ENDPOINTS` from plan section 3.4. | 2026-09-20: `uv run pytest -q tests/contracts/test_knowledge.py` → 44 passed | None | M1-T02 |
| M1-T02 | DONE | `src/episalpha/contracts/research.py`, `src/episalpha/contracts/errors.py`, `tests/contracts/test_research.py` — RunRequest, SnapshotManifest, ThesisAssertion, Thesis, RunRecord, ValidationReport, RuntimeContext, StageResult, Usage, Budgets; transition validator; eight frozen error codes. | 2026-09-20: `uv run pytest -q tests/contracts/test_research.py` → 60 passed | None | M1-T03 |
| M1-T03 | DONE | `src/episalpha/evidence/temporal.py`, `tests/evidence/test_temporal.py` — pure eligibility functions implementing plan section 3.5 rules 1-9, including the version-A/version-B selection fixture. | 2026-09-20: `uv run pytest -q tests/evidence/test_temporal.py` → 19 passed | None | M1-T04 |
| M1-T04 | DONE | `src/episalpha/research/validation.py`, `tests/research/test_validation.py` — reference resolution, relation endpoint/kind checks, exact quotation verification, derivation checks, assertion coverage, semantic-status enforcement. | 2026-09-20: `uv run pytest -q tests/research/test_validation.py` → 20 passed | None | M2-T01 |
| M0-T02b | DONE | `src/episalpha/settings.py` (SourceFamily, ProvenanceStrength, SourceConfig, expanded SourcesConfig), `config/demo.example.toml`, `tests/contracts/test_settings.py` — full TradingAgents source set with provenance, resolved demo corpus and price source. | 2026-09-20: `uv run pytest -q tests/contracts/test_settings.py` → 40 passed; four standard checks pass | Alpha Vantage key not yet issued | M2-T01 |
| M2-T01 | DONE | `src/episalpha/storage/db.py`, `repository.py`, `migrations/001_initial.sql`, `tests/evidence/test_repository.py` — typed node registry so relation endpoints are real foreign keys; WAL, FK enforcement, busy timeout, explicit transactions; versioned assessments; runs with a unique idempotency key; stage checkpoints and usage; FTS5 over spans kept in step by triggers. | 2026-09-20: `uv run pytest -q tests/evidence/test_repository.py` → 26 passed | None | M2-T02 |
| M2-T02 | DONE | `src/episalpha/storage/objects.py`, `src/episalpha/evidence/parsing.py`, `tests/evidence/test_objects_and_spans.py` — SHA-256 content-addressed store with atomic writes and read-time verification; deterministic NFC text normalization; script/style/comment content stripped; spans cut from the text so a quotation cannot be invented. | 2026-09-20: `uv run pytest -q tests/evidence/test_objects_and_spans.py` → 27 passed | None | M2-T03 |
| M2-T03 | DONE | `src/episalpha/connectors/prices.py`, `connectors/filings.py`, `tests/fixtures/connectors/*`, `tests/evidence/test_connectors.py` — Alpha Vantage daily prices and SEC EDGAR filings, both driven by an injected transport so the default suite is offline; EDGAR host allowlist and fair-access User-Agent. | 2026-09-20: `uv run pytest -q tests/evidence/test_connectors.py` → 32 passed | None | M2-T04 |
| M2-T04 | DONE | `src/episalpha/evidence/snapshots.py`, `eval_cases/manifests/*` (3 real), `eval_cases/development/*` (5 synthetic), `tests/evidence/test_snapshots.py` — deterministic content hash, closed `SnapshotView`, recorded source completeness. | 2026-09-20: `uv run pytest -q tests/evidence/test_snapshots.py` → 32 passed | Demo case mapping still PROVISIONAL; owner checkpoint pending | M3-T01 |

## Gate results

### Gate G0 — offline PASSED, live PARTIAL (model route verified; Hermes runtime unproven)

```
uv run episalpha --version                                        -> 0.1.0
uv run pytest -q tests/contracts/test_settings.py tests/integration/test_package.py -> passed
uv run pytest -q -m live tests/integration/test_hermes_probe.py   -> 2 passed in 16.93s
```

The model route is verified. The Hermes side is **not** fully verified, and this is recorded
rather than papered over:

- **Install path resolved.** Owner approved the git install. A `git+https` wheel build is
  refused by upstream on purpose (`RuntimeError: Building wheels or sdists for hermes-agent is
  not supported. Hermes is distributed via the shell installer, Docker image, or Nix.`). Cloning
  at `c1488ac` and running `uv pip install -e .` into an isolated virtualenv succeeded, so every
  API fact is now read from `0.21.3` itself rather than the older PyPI `0.19.0`. **M3 should use
  the Docker image** — upstream's supported distribution, and already the isolation plan
  section 4.2 requires.
- **Tool path identified, not proven.** `AIAgent.__init__` exposes none of `mcp_servers`,
  `tools`, `extra_tools`, `custom_tools`, `tool_registry`; `create_custom_toolset` composes tool
  *names* only. MCP servers are file-configured (`mcp.json` under `~/.hermes`) and surface with
  an `mcp_` prefix that `create_custom_toolset` can allowlist. M3-T01/M3-T03 must demonstrate
  this end to end before the runtime is built on it.
- No end-to-end Hermes agent turn has been run. M0-T03 stops before building a runtime.

Full findings: `docs/implementation/hermes_probe.md`; machine-readable: `config/runtime.lock.json`.

### Gate G1 — PASSED

```
uv run pytest -q tests/contracts tests/evidence/test_temporal.py tests/research/test_validation.py
  -> 174 passed
uv run ruff check .            -> All checks passed
uv run ruff format --check .   -> 21 files already formatted
uv run mypy src/episalpha      -> Success: no issues found in 11 source files
uv run pytest -q -m "not live" -> 176 passed, 2 deselected
```

Re-run after the source-model expansion (M0-T02b): `uv run pytest -q -m "not live"` -> 185 passed,
2 deselected; all four standard checks still pass.

**Schema version is now frozen at `1`** (`episalpha.contracts.knowledge.SCHEMA_VERSION`). Further
contract changes require an explicit migration or compatibility decision.

### Gate G2 — PASSED (with one owner checkpoint outstanding)

```
uv run pytest -q tests/evidence   -> 139 passed
uv run ruff check .               -> All checks passed
uv run ruff format --check .      -> 34 files already formatted
uv run mypy src/episalpha         -> Success: no issues found in 20 source files
uv run pytest -q -m "not live"    -> 305 passed, 2 deselected
```

The gate also requires that a reviewer can open raw bytes, normalized text, selected spans and
the exact manifest for each demo case, and that a future-source rejection and a source-failure
case are included. The machinery for all of this is in place and tested
(`ObjectStore.get`, `extract_text`, `SnapshotView`, `verify_snapshot`; the synthetic
`future-source` and `source-failure` variants). **The owner checkpoint is outstanding:** the
three real cases have not been ingested from live SEC payloads, and their key quotations have
not been manually inspected. Until that happens the case mapping stays `PROVISIONAL`.

**Schema note.** `SnapshotManifest` gained `source_completeness`, a tuple defaulted to empty.
This is additive and backward compatible — manifests written before it still validate — so
schema version stays `1`. Recorded here because section 3.2 is frozen and any contract change
needs an explicit compatibility decision.

## Owner inputs (plan section 1.4)

| Input | Status | Effect |
|---|---|---|
| Research model / provider / credential | **RESOLVED** | Ollama, `glm-5.3`, `https://ollama.com/v1`, credential `ENV:ollama_api_key` from the git-ignored `.env`. Verified by live probe. Note: the id is `glm-5.3` on the cloud endpoint; `glm-5.3:cloud` is the local-daemon form. |
| Three demo companies + one theme | **RESOLVED** | Theme: company guidance and demand changes. LULU (CIK 0001397187) supported-thesis case; TSCO (0000916365) conflicting-evidence case; CALX (0001406666) insufficient-evidence case. CIKs verified against SEC `company_tickers.json`. **Case mapping is PROVISIONAL** — it reflects public reporting, not verified filing content, and M2-T04 must confirm or reassign it. |
| Price source and permitted local use | **RESOLVED and VERIFIED** | `alpha_vantage` `TIME_SERIES_DAILY`, credential `ENV:alpha_vantage_api_key`. Key supplied 2026-09-20 and confirmed live against LULU, TSCO and CALX (100 daily bars each, latest 2026-09-18). `sources.missing_credentials` is now empty. Two constraints found: the free tier refuses back-to-back calls (~1 req/sec) returning HTTP 200 with an `Information` key and no data, and `TIME_SERIES_DAILY_ADJUSTED` is premium so the free close is **unadjusted**. |
| Source scope | **RESOLVED (scope expansion)** | Owner chose the full TradingAgents shape: market, news, social, fundamentals, macro. This exceeds plan section 1.2's envelope of filings plus one price path. Each source now carries a `provenance` value (`primary`/`secondary`/`unverified`); the filings source must be `primary`, and social sources ship disabled. |
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

The "Start here" section now points at M2-T01 rather than M0-T01.

## Repository note (not a task)

`EpisAlpha_Architecture_and_Implementation_Blueprint.md:Zone.Identifier` is tracked in commit
`8b7b4c6` and is **not** matched by the `.gitignore` pattern `*.Zone.Identifier`, because the
filename separator is `:` rather than `.`. Owner decision needed: `git rm --cached` the file and
change the pattern to `*Zone.Identifier`.
