# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
uv sync --all-groups                    # install (Python 3.12 + uv)
uv run ruff check .
uv run ruff format --check .
uv run mypy src/episalpha                # strict mode, owned code only
uv run pytest -q -m "not live"           # default suite: offline, no credentials
uv run pytest -q tests/research/test_runner.py -k <expr>     # one file / one test
uv run python scripts/diagnose.py        # end of every task; appends implementation/logs/diagnose.jsonl

uv run episalpha demo seed               # synthetic demo corpus into .episalpha/
uv run episalpha research run --case supported   # --runtime fake (default) => [FIXTURE] output
uv run episalpha replay <run_id>
uv run streamlit run apps/streamlit_app.py        # binds 127.0.0.1:8501

set -a; source .env; set +a              # live only; every live call needs fresh owner approval
uv run pytest -q -m live tests/integration/test_hermes_probe.py
```

CLI exit codes: 0 completed · 2 invalid request · 3 rejected · 4 failed/timed out ·
5 abstained/partial · 6 cancelled.

Docker (any Linux host; see `HANDOFF.md`): `docker compose build`, `docker compose run --rm check`
(the four checks + diagnose), `docker compose up -d phoenix ui`, `docker compose run --rm cli ...`.
Live Hermes runs add `-f compose.live.yaml` (Docker socket; owner approval per live run). The repo
must be mounted at the same absolute path as on the host, so always run compose from the repo root.

All four checks (`ruff check`, `ruff format --check`, `mypy`, `pytest -m "not live"`) run at every
milestone gate. Tests requiring network, credentials, or a real model route must carry the `live`
marker; `tests/conftest.py` has an autouse guard that fails any non-loopback connect or DNS lookup
in unmarked tests. Shared fixtures import as `fixtures.*` (`tests/fixtures/`).

## What this repository is

EpisAlpha is an evidence-grounded personal investment research workbench: a local, browser-first
tool that produces a structured thesis where every material assertion traces to an exact source
passage, and that can compare a baseline research procedure against a bounded offline challenger.

The design is fully specified in two documents. Read the relevant sections before building:

- `EpisAlpha_MVP_Milestone_Implementation_Plan.md` — **governs v0.1.** Frozen contracts,
  controlled vocabulary, temporal rules, repository layout, milestones M0–M7 with task cards
  and gates. Where it disagrees with the blueprint, this plan wins.
- `EpisAlpha_Architecture_and_Implementation_Blueprint.md` — longer-term direction (Sentinel,
  paper portfolio, evolution lab, evaluation science, trust zones). Do not load it by default;
  consult specific sections when the plan points there.

Status and the next task: `implementation/STATUS.md` (source of truth). Setup, owner blockers and
live-run notes: `HANDOFF.md` (`SESSION_HANDOFF.md` is superseded, kept for history). Anything in
plan §4.1 not present on disk is target structure, not existing code.

Research model route (amendment A9): OpenRouter `nvidia/nemotron-3-ultra-550b-a55b:free` via
`ENV:openrouter_api_key`, verified live by M0-T04 on 2026-10-10 (served by Nvidia, no fallbacks).
The free tier allows 20 req/min and 50 req/day (1,000 with ≥$10 lifetime credits). Budget live
tests accordingly.

Learning (amendment A13): **learn offline, act frozen.** A run never changes the skills it uses
(read-only, versioned, hash recorded); it may only `propose_skill` as data. Promotion goes
screen → offline evaluation → **owner approval**, and is revocable (milestone M8, after G7).
Hermes' native memory, background review, curator and Skills Hub stay off.

## How work is executed here

Work proceeds **one task card per session**, in dependency order (M0 → M1 → … → M7), each
milestone gated by the preceding gate's checks actually passing. **Start every session at
`implementation/README.md`.** Load exactly `implementation/CONSTITUTION.md`, the phase
`CONSTITUTION.md`, and one task pack (`implementation/M<n>-*/tasks/*.md`), then work its steps:
**Plan → Verify → Build → Test → Diagnose**.

- Target 1–3 implementation files plus one focused test file per task. Split the task rather than
  exceeding it.
- Read only the relevant plan sections, the current task card, its contracts, and directly related
  code/tests.
- Do not implement later-milestone features to make the current task easier.
- Record each task in the phase `PROGRESS.md` and `implementation/STATUS.md`: Task / Status /
  Changes / Verification (exact command + actual result) / Blocker / Next. Append every attempt
  to the task's `*.journal.md`. Gate results go in the phase `GATE.md`.
  `docs/implementation/progress.md` keeps only the cross-cutting owner inputs, findings and
  amendments.
- **Diagnose layer (A11, A14):**
  - Run `uv run python scripts/diagnose.py` at the end of each task.
  - Every boundary, AI or not, emits an OpenTelemetry span via
    `episalpha.observability.span`. One trace per research run (root `research.run`,
    `session.id` = run ID).
  - Spans go to `<data_root>/logs/spans.jsonl` (metadata only) and, when `otlp_endpoint` is set
    under `[observability]`, to a local Arize Phoenix on `127.0.0.1:6006` (full content).
  - Secrets are redacted before any exporter.
  - Phoenix and the logs are diagnostic, never canonical. A Phoenix outage never fails a run.
- Commits are an explicit owner action; the plan does not authorize automatic commits or pushes.
- Stop and report **BLOCKED** when an upstream interface is unverified, credentials for a required
  live check are missing, a contract conflicts, or scope needs an unapproved architectural change.
  Escalate after two failed bounded attempts at the same issue.

## Architecture

One research run, top to bottom (`src/episalpha/` unless noted):

```text
cli.py (Typer) / apps/streamlit_app.py      thin shells; never run a model on the UI render path
  -> research/services.py     admission, idempotency, the single job slot, run views
  -> research/runner.py       8 stages: admit -> freeze snapshot -> researcher -> validate + map IDs
                              -> critic -> synthesizer -> validation (<=1 bounded repair) -> persist
       -> runtime/port.py     ResearchRuntimePort: one stage at a time
            fake.py           replays tests/fixtures/runtime/*.json, every payload labelled fixture
            hermes.py         host side; launches worker/hermes_stage.py in Hermes' own env
              sandbox.py      worker container on an --internal network, reaching only:
              model_relay.py    the sole holder of the provider key; one route, fails closed
              mcp_server.py     snapshot-bound typed tools (tools.py) over MCP Streamable HTTP
       -> runtime/candidates.py              parse each stage's submit_<stage> payload
       -> research/validation.py, derivations.py   structural checks; recompute derived numbers (A8)
       -> research/artifacts.py              <data_root>/runs/<run_id>/ canonical JSON + index.json
evidence/    parsing (deterministic spans), temporal eligibility, frozen hashed snapshots
connectors/  SEC EDGAR filings, XBRL company facts (point-in-time), Alpha Vantage prices
storage/     sqlite3 + numbered SQL migrations, typed repository, content-addressed object store
```

- **Agents propose; deterministic systems dispose.** The runtime returns *candidate* research;
  the runner validates, assigns canonical IDs (`<run_id>.<key>`), refuses any ID that already
  exists, and only then passes records to later stages via `RuntimeContext`.
- **The input snapshot is immutable.** Newly generated claims/hypotheses live in a separate
  current-run record set and may cite only eligible source spans or already-validated current-run
  records. Final artifacts keep both the manifest and the generated records.
- **Hermes never enters the application venv.** It exact-pins its dependencies, so only
  `worker/hermes_stage.py` (stdlib + Hermes, run with Hermes' interpreter) imports it. The pin
  (Hermes 0.21.3, commit and worker image ID) is in `config/runtime.lock.json`;
  `scripts/setup_worker.py` rebuilds it. Never globally relax typing for an upstream package.
- Connectors take an injected `Transport` callable, so tests feed `tests/fixtures/connectors/`
  instead of the network. **Connectors never infer conclusions**; exporters (Obsidian/Markdown)
  are derived and never canonical; the evaluator never executes candidate code; validation labels
  live outside any agent-accessible path.
- Storage is stdlib `sqlite3` with WAL, foreign keys, busy timeout, short transactions — no ORM.
  v0.1 allows one active research job.
- Stage prompts live in `harnesses/baseline/`; demo and evaluation cases in `eval_cases/`
  (case → company mapping is PROVISIONAL until the G2 owner checkpoint).

## Configuration and data

- `config/demo.toml` (copy of `config/demo.example.toml`) is loaded into one validated `Settings`
  object (`settings.py`). Unknown keys are rejected at every level. Relative `project_root`
  resolves from the config file's own directory and `data_root` under it — never from the CWD.
- All limits and budgets (plan §3.8) live in `Settings.limits`; no scattered constants.
- Credentials appear only as `ENV:<name>` references, resolved lazily (a missing key returns
  `None`, so offline work never fails). Values live in the git-ignored `.env`; never print them —
  read names only (`cut -d= -f1 .env`).
- `.episalpha/` (git-ignored data root): `app.sqlite3`, `objects/`, `runs/<run_id>/`,
  `logs/spans.jsonl`, `phoenix/`, `vendor/` (Hermes clone and venv).

## Non-negotiable domain rules

**Six clocks, never collapsed:** economic event time · source publication time · when that exact
version became publicly available · when EpisAlpha actually captured it (`ingested_at`) · research
cutoff · actual run execution time. A publication date alone never proves today's fetched version
existed then; unverified availability falls back to `first_capture` as the conservative eligibility
time. Retain old document versions and select the latest *qualifying* version as of the cutoff.
A claim created today from old evidence keeps today's `created_at`. Historical runs must display:
"Retrospective research; model training knowledge may include later events."

**Frozen vocabulary** (plan §3.3) — extending it is a schema change requiring owner approval:
`epistemic_status`: reported | derived | hypothesized ·
`semantic_review_status`: unreviewed | supported | partially_supported | unsupported ·
`research_stance`: investigate | watch | abstain ·
`relation_predicate`: ISSUED_BY | HAS_SPAN | REPORTS | ABOUT | SUPPORTS | CONTRADICTS | DERIVED_FROM
(no `CAUSES` in v0.1) · `research_mode`: forward_research | historical_reconstruction.

Valid schema plus a clean citation does **not** make a claim `supported` — only a recorded
`SemanticAssessment` does, and assessments are versioned, never overwritten. Every user-visible
material statement goes through `ThesisAssertion` with claim/hypothesis references; never add a
free-text summary field that bypasses them. Numbers are reported (cited span) or recomputed by a
registered derivation — the model never supplies a computed value (A8). An `unverified` source
cannot be the sole support for an assertion (A2).

**Honest failure states:** `ABSTAINED` (essential evidence missing) ≠ `REJECTED` (unrepairable
invalid references) ≠ `PARTIAL` ≠ `FAILED`/`TIMED_OUT`. A provider outage is never translated into
a valid abstention, `SOURCE_FAILED` is not `NO_DATA`, and partial work is preserved when a run
fails. Unknown usage/cost stays unknown (`None`), never estimated.

**Conventions:** application-generated filesystem-safe IDs (user titles and model text are never
paths); timezone-aware UTC timestamps with explicit offsets; money and financial measurements as
decimal strings plus units, never raw floats.

## Verification integrity

- Never weaken an assertion, skip a failing test, or regenerate an expected answer to get a pass.
- Never claim a live integration passed using `FakeRuntime`; `FakeRuntime` output is always labeled
  as a fixture. A blocked live gate stays blocked.
- Do not invent upstream Hermes API arguments, commit IDs, model capabilities, or evaluation
  results — pin and record what was actually inspected.
- Human-owned evidence annotations and evaluation labels are not repair targets.
- Dependency policy is deliberately minimal: Pydantic, Typer, Streamlit, OpenTelemetry (HTTPX is
  permitted by the plan but not used yet); pytest/Ruff/mypy for dev. Add a dependency only when a
  specific task requires it. Coding-model choice and research-model choice are independent; no
  model names in code — the research route lives only in `config/*.toml`.
