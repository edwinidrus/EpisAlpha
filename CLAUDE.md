# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
uv sync --all-groups                    # install (Python 3.12 + uv)
uv run episalpha --version
uv run ruff check .
uv run ruff format --check .
uv run mypy src/episalpha                # strict mode, owned code only
uv run pytest -q -m "not live"           # default suite: offline, no credentials
uv run pytest -q -m live tests/integration/test_hermes_probe.py   # opt-in live checks
uv run pytest -q tests/contracts/test_settings.py::test_name      # single test
```

All four checks (`ruff check`, `ruff format --check`, `mypy`, `pytest -m "not live"`) run at every
milestone gate. Tests requiring network, credentials, or a real model route must carry the `live`
marker; the default suite must pass with no external network.

## What this repository is

EpisAlpha is an evidence-grounded personal investment research workbench: a local, browser-first
tool that produces a structured thesis where every material assertion traces to an exact source
passage, and that can compare a baseline research procedure against a bounded offline challenger.

**The code is a small skeleton; the design is fully specified in two documents.** Read them before
building anything:

- `EpisAlpha_MVP_Milestone_Implementation_Plan.md` — **governs v0.1.** Frozen contracts,
  controlled vocabulary, temporal rules, repository layout, milestones M0–M7 with task cards
  and gates. Where it disagrees with the blueprint, this plan wins.
- `EpisAlpha_Architecture_and_Implementation_Blueprint.md` — longer-term direction (Sentinel,
  paper portfolio, evolution lab, evaluation science, trust zones). Do not load it by default;
  consult specific sections when the plan points there.

Current state: M0–M2 implemented (gates G0 offline, G1, G2 passed; G0 live partial — Hermes
runtime unproven). Gates G0–G2 are reopened by amendments A8–A11. M0-T04 (OpenRouter route) DONE.
Next task: `M0-T05`, then `M0-T06`, `M0-T07`, `M1-T05`, `M2-T05`, `M2-T06`, `M3-T01`. `implementation/STATUS.md` is the source of truth for task status; anything in plan
§4.1 not present on disk is target structure, not existing code.

Research model route (amendment A9): OpenRouter `nvidia/nemotron-3-ultra-550b-a55b:free` via
`ENV:openrouter_api_key`, **verified live by M0-T04 on 2026-10-10** (served by Nvidia, no fallbacks). The free tier allows 20 req/min and
50 req/day (1,000 with ≥$10 lifetime credits). Budget live tests accordingly.

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
  - Run `uv run python scripts/diagnose.py` at the end of each task (from M0-T05).
  - Every boundary, AI or not, emits an OpenTelemetry span via
    `episalpha.observability.span` (from M0-T06). One trace per research run.
  - Spans go to `<data_root>/logs/spans.jsonl` (metadata only) and, when configured, to a
    local Arize Phoenix on `127.0.0.1:6006` (full content; M0-T07).
  - Secrets are redacted before any exporter.
  - Phoenix and the logs are diagnostic, never canonical. A Phoenix outage never fails a run.
- Commits are an explicit owner action; the plan does not authorize automatic commits or pushes.
- Stop and report **BLOCKED** when an upstream interface is unverified, credentials for a required
  live check are missing, a contract conflicts, or scope needs an unapproved architectural change.
  Escalate after two failed bounded attempts at the same issue.

## Architecture (target)

```text
Browser (Streamlit) / CLI (Typer)
  -> application services: jobs, idempotency, snapshots, state transitions, persistence
  -> research runner
       -> snapshot-bound typed tools
       -> isolated Hermes worker subprocess
       -> single-route model relay
  -> deterministic validator
  -> canonical records + run artifacts
       -> evidence/relationship views, Obsidian export, offline evaluation reports
```

Directional rules that shape most code:

- **Agents propose; deterministic systems dispose.** The Hermes worker returns *candidate* research;
  the host validates, assigns canonical IDs, and only then passes records to later stages via
  `RuntimeContext`. A model can never overwrite an existing canonical ID.
- **The input snapshot is immutable.** Newly generated claims/hypotheses live in a separate
  current-run record set and may cite only eligible source spans or already-validated current-run
  records. Final artifacts keep both the manifest and the generated records.
- **Exporters are never canonical.** Obsidian/Markdown output is derived, one-way.
- **Connectors never infer conclusions**; the evaluator never executes candidate code; validation
  labels live outside any agent-accessible path.
- Isolate untyped upstream (Hermes) imports inside `runtime/hermes.py`; never globally relax typing
  to accommodate an upstream package.
- Storage is stdlib `sqlite3` with WAL, foreign keys, busy timeout, short transactions — no ORM.
  v0.1 allows one active research job.

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
free-text summary field that bypasses them.

**Honest failure states:** `ABSTAINED` (essential evidence missing) ≠ `REJECTED` (unrepairable
invalid references) ≠ `PARTIAL` ≠ `FAILED`/`TIMED_OUT`. A provider outage is never translated into
a valid abstention, and partial work is preserved when a run fails.

**Conventions:** application-generated filesystem-safe IDs (user titles and model text are never
paths); timezone-aware UTC timestamps with explicit offsets; money and financial measurements as
decimal strings plus units, never raw floats. Budgets and limits (plan §3.8) live in one validated
settings object, not scattered constants.

## Verification integrity

- Never weaken an assertion, skip a failing test, or regenerate an expected answer to get a pass.
- Never claim a live integration passed using `FakeRuntime`; `FakeRuntime` output is always labeled
  as a fixture. A blocked live gate stays blocked.
- Do not invent upstream Hermes API arguments, commit IDs, model capabilities, or evaluation
  results — pin and record what was actually inspected.
- Human-owned evidence annotations and evaluation labels are not repair targets.
- Dependency policy is deliberately minimal (Pydantic, Typer, HTTPX, Streamlit; pytest/Ruff/mypy for
  dev). Add a dependency only when a specific task requires it. Coding-model choice and research-model
  choice are independent; never hard-code a product dependency on a model brand name.
