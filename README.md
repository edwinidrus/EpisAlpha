# EpisAlpha

Evidence-grounded personal investment research workbench.

Current implementation scope: milestone M0 (bootstrap, settings, route probe) and milestone M1
(canonical contracts). It provides a typed Python package, developer tooling, a versioned CLI
entry point, one validated settings object owning every runtime limit, the frozen knowledge and
research contracts at schema version 1, the temporal eligibility policy, and the deterministic
structural validator.

Not implemented yet: persistence, source connectors, snapshots, the Hermes runtime, the research
runner, the browser workbench, and the evaluation harness. Progress and gate results are tracked
in `docs/implementation/progress.md`.

## Development

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --all-groups
uv run episalpha --version
uv run ruff check .
uv run ruff format --check .
uv run mypy src/episalpha
uv run pytest -q -m "not live"
uv run pytest -q tests/contracts/test_settings.py
```

Live checks make real, paid model calls and are excluded by default:

```bash
set -a; source .env; set +a
uv run pytest -q -m live tests/integration/test_hermes_probe.py
uv run python scripts/probe_hermes.py config/demo.toml
```

## Configuration

```bash
cp config/demo.example.toml config/demo.toml
```

The file has five tables: `[paths]`, `[provider]`, `[demo]`, `[sources]`, and `[limits]`. Unknown
keys are rejected, in nested tables too, so a typo fails loudly instead of being ignored.

**Sources.** The source set follows the TradingAgents reference architecture across five families
(market, news, social, fundamentals, macro). Each source carries a `provenance` value — `primary`
(the issuer's or regulator's own document), `secondary` (a report *about* one), or `unverified`
(public commentary with no availability guarantee). This is not a quality score; it records what
kind of thing the source is. The filings source must be `primary`, and social sources ship
disabled because they cannot establish that anything is true.

Two credentials are referenced: `ollama_api_key` for the model route and `ALPHAVANTAGE_API_KEY`
for prices. A missing key never fails the load — `Settings.sources.missing_credentials` lists
which enabled sources cannot currently authenticate.

**Path rule.** A relative `project_root` resolves from the configuration file's own directory, and
a relative `data_root` resolves under `project_root`. The process working directory is never used,
so loading the same file from anywhere gives the same paths.

**Credential rule.** Credentials are environment *references*, never values:

```toml
api_key_env = "ENV:ollama_api_key"   # the variable NAME, never the key
```

```bash
set -a; source .env; set +a          # .env is git-ignored and never read by the application
```

The configuration file therefore contains no secrets and is safe on disk and in backups. The
reference is resolved lazily by `ProviderRoute.credential()` at the moment of use; if the variable
is absent it returns `None` rather than failing, so offline work is never blocked by a missing key.

**Limits.** Every numeric budget from the plan's section 3.8 lives in `[limits]` and nowhere else
in the codebase. `eur_cap` is deliberately rejected in v0.1: without cost reservation and verified
pricing the application cannot honour a hard spending cap, so it reports cost as unknown instead of
claiming one.

## Offline setup

Loading settings makes no network calls and requires no credentials. The default test suite
(`uv run pytest -q -m "not live"`) runs with no network access and no provider account. Tests that
need a real model route or external service carry the `live` marker and are excluded by default.

Owner inputs that are still unresolved — the three demo companies and theme, and the price source —
are left explicitly unset rather than given placeholder defaults; `Settings.unresolved_owner_inputs`
lists them, and their BLOCKED status is tracked in `docs/implementation/progress.md`.
