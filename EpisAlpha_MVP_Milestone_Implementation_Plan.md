# EpisAlpha MVP — Milestone Implementation Plan

**Version:** 1.5  
**Prepared:** 20 September 2026 · **Amended:** 20 September 2026 after gates G0/G1; 10 October 2026 (A8–A14)  
**Status:** M0, M1 and M2 implemented and gated. Amendments below record verified facts and owner decisions; everything else remains as issued.  
**Audience:** Solo builder and coding agents, including GPT-5.6 Terra / GLM-5.3-class models.  
**Architecture approach:** Lightweight arc42-style constraints and quality scenarios, organized around executable delivery milestones.  
**Companion:** [Architecture and Implementation Blueprint](./EpisAlpha_Architecture_and_Implementation_Blueprint.md)

> Build a personal, browser-first research workbench that explains what it believes, where evidence comes from, what contradicts it, and how a bounded research-procedure change performs against a fixed evaluation set.

This plan narrows the companion blueprint for v0.1. Where their MVP scope differs, this plan governs the proposed v0.1 implementation. The blueprint remains the longer-term direction.

Passing the gates establishes tested behavior, not perfect model accuracy, proven alpha, or production readiness. Coding-model capability must be compensated for through bounded tasks, explicit contracts, and independent verification.

---

## 0. Amendment record (v1.1–v1.5)

Every change below replaces an assumption with something observed, or records an owner decision.
Sections not listed are unchanged. Evidence: `docs/implementation/hermes_probe.md`,
`config/runtime.lock.json`, `docs/implementation/progress.md`.

| # | Section | Change | Why |
|---|---|---|---|
| A1 | 1.2, 1.4 | Owner inputs resolved: Ollama `glm-5.3`; LULU/TSCO/CALX; Alpha Vantage prices | Probed and verified live |
| A2 | 1.2, 3.3, 3.4 | Source set widened to the TradingAgents shape; every source carries a `provenance` value | Owner decision; mixing filings with forum posts needs the distinction |
| A3 | 3.6, 3.8, M3-T02 | The relay must **not** use `response_format`; structured output comes from forced `tool_choice` | The route accepts `response_format` and silently ignores it |
| A4 | 3.8 | Added per-source request budgets | Alpha Vantage free tier throttles at ~1 request/second |
| A5 | 4.2, M0-T03 | Hermes installs via Docker/installer/Nix or an editable clone, never a built wheel | Upstream `setup.py` refuses wheel and sdist builds |
| A6 | 2.6 (new) | Point-in-time price caveat: free-tier close is **unadjusted** | `TIME_SERIES_DAILY_ADJUSTED` is a premium endpoint |
| A7 | 4.1 | `tests/conftest.py` and `tests/fixtures/` added to the target structure | Shared fixtures must import across test directories |
| A8 | 1.2, 3.4, 3.6, M1-T05 (new), M2-T05 (new), M3-T01, M4-T04, M5-T02, M6-T01, 15.3 | **Quantitative evidence layer (v1.2).** Every number is either reported (cited span) or derived by a versioned deterministic method the validator recomputes; point-in-time SEC XBRL fundamentals; a host-side compute tool. No returns, backtests, factor models or alpha claims in v0.1 | LLM multi-step financial arithmetic errs 10–20% or worse (FAITH 2025); M1-T04's "deterministic derivation verification" only resolved input references and never recomputed a value; owner chose "Core numbers" scope on 2026-10-10 |
| A9 | 1.2, M0-T04 (new), M3-T02 | **Research route moves to OpenRouter** `nvidia/nemotron-3-ultra-550b-a55b:free` (`https://openrouter.ai/api/v1`, `ENV:openrouter_api_key`). **Unverified until the M0-T04 live probe**; Ollama `glm-5.3` stays in the lock file as history. Free tier: 20 req/min; 50 req/day (1,000 with ≥$10 lifetime credits) — at most 6 runs/day at 8 requests/run; the M6 campaign needs credits or a multi-day schedule. `:free` data-logging policy unconfirmed | Owner decision 2026-10-10 |
| A10 | 17, all task cards | **Execution layer moves to `implementation/`**: per-phase CONSTITUTION/PLAN/PROGRESS/GATE and self-contained task packs (Plan → Verify → Build → Test → Diagnose). This plan stays the source of contracts (§§1–4) and the acceptance matrix (§14); task status lives in `implementation/STATUS.md` | Owner request: one focused context per coding session |
| A11 | M0-T05, M0-T06, M2-T06 (new); M3+ cards | **Diagnose layer.** Implementation level: `scripts/diagnose.py` (checks, tests per directory, docs↔disk traceability, regression vs history) plus an append-only journal per task. Operational level: `src/episalpha/observability.py` (stdlib JSON-lines events, `contextvars` correlation, credential redaction); every boundary emits events; logs are diagnostic, never canonical. Acceptance rows A25 (wrong derived number) and A26 (secret in any log) added in `implementation/M7-acceptance/PLAN.md` | Owner request: white-box visibility of what works and what does not |
| A12 | M3 (constitution 12–14, M3-T01..T04), M4-T01, acceptance A27–A29 | **Runtime hardening.** The relay forwards an allowlist of body fields (rejects OpenRouter `plugins`/`:online`/`models`/`provider`/`openrouter:web_search`); worker image pinned by digest, non-root, `cap_drop: ALL`, read-only rootfs, pids/memory limits, external DNS blocked; worker output read without following symlinks; rootless Docker or userns-remap recommended (host is rootful Docker 29.1.3 in WSL); Hermes native memory/background review/curator/Skills Hub off at runtime | Owner security review 2026-10-10; CVE-2024-29018 (DNS from internal networks); Hermes docs: Docker mode skips its dangerous-command checks |
| A13 | Global constitution §VIII, M3/M4 hooks, new milestone M8 (`implementation/M8-learning/`), acceptance A30–A31 | **Safe continuous learning.** Learn offline, act frozen: runs use a read-only versioned skill set (hash in the harness hash) and may only `propose_skill` as data; host screens deterministically, evaluates offline (paired, no regression + targeted gain), **owner approves every promotion**; provenance-linked cascade revocation; historical runs use skills promoted ≤ cutoff. M8 follows G7 | Owner wants the non-frontier model to improve over time; procedural skills help weaker models most, but self-generated skills can degrade quality and can be poisoned (SkillsBench; SkillJack, arXiv 2608.03509) |
| A14 | Global constitution §VII, M0-T06 (rewritten), M0-T07 (new), M2-T06, M3/M4/M5/M6 span wording, M8-T05 (new), acceptance A32 | **Whole-system Diagnose service.** OpenTelemetry tracing for every boundary — runner, connectors, tools, relay, validator, sandbox, CLI/UI, evaluation, learning — one trace per research run (OpenInference span kinds). Exporters: JSONL fallback (metadata only, always on) and a **local Arize Phoenix** (`127.0.0.1:6006`, OTLP/HTTP, SQLite volume, telemetry off, pinned digest; full content per owner decision; secrets redacted before any exporter). Phoenix is never canonical; an outage never fails a run. M8-T05 turns traces and owner annotations into a deterministic failure-cluster report that grounds M8/M6 improvements; annotations are never evaluation labels. New deps: `opentelemetry-api`, `-sdk`, `-exporter-otlp-proto-http` | Owner request 2026-10-10: capture the whole system, not only the model, as grounding for improvement. Phoenix: Elastic License 2.0, single container, OTel-native; Langfuse self-host needs Postgres+ClickHouse+Redis+S3 |

---

## 1. Product scope and fixed decisions

### 1.1 Demo outcome

A user can:

1. Select one of three company research cases and a research cutoff.
2. Run a bounded Hermes workflow or open a clearly labeled saved run.
3. Inspect a thesis, counter-case, unknowns, and next research question.
4. Follow each material assertion to a claim and exact source passage.
5. Inspect a small evidence graph and export it to Obsidian.
6. Compare a baseline procedure with one bounded offline challenger.
7. See abstention, partial results, rejection, and provider failure honestly.

The first audience is the owner, using a local Linux/WSL environment. No public hosting or multi-user service is assumed.

### 1.2 v0.1 envelope

| Concern | Fixed initial decision |
|---|---|
| Product | Personal research workbench |
| Demo corpus | Three named companies; one narrow theme; three curated demo cases |
| Theme | Company guidance and demand changes (**resolved**) |
| Companies | **LULU** (CIK 0001397187), **TSCO** (0000916365), **CALX** (0001406666); CIKs verified against SEC `company_tickers.json` |
| Cases | Supported thesis; conflicting evidence; insufficient evidence. **The mapping of company to case is provisional** — it reflects public reporting, not verified filing content, and M2-T04 must confirm or reassign it |
| Sources | **Amended (A2).** Five families following the TradingAgents reference architecture: fundamentals (`sec_edgar`, primary), market (`alpha_vantage`, primary), news (`alpha_vantage_news`, secondary), macro (`fred`, disabled), social (`reddit`, `stocktwits`, unverified, **disabled**). Enabled by default: the first three |
| Price path | `alpha_vantage` `TIME_SERIES_DAILY`, free tier. See 2.6 — the free close is **unadjusted** |
| Numeric fundamentals | **Amended (A8).** `sec_xbrl`: SEC `companyfacts` API, `primary`, no key, same User-Agent and host allowlist as `sec_edgar`. Facts are selected by `filed <= cutoff`; the `frames` API is **never** used for a historical cutoff because it returns the last-filed (possibly restated) value |
| Research horizon | One horizon: 20 trading days, labeled research context |
| User surface | Streamlit browser application |
| Automation surface | Thin Typer CLI sharing application services |
| Core language | Python 3.12 (**verified**: Hermes `requires-python >=3.11,<3.14`) |
| Research model route | **Amended (A9), verified 2026-10-10 by M0-T04 (live probe; forced `tool_choice` honoured, served by Nvidia, no fallbacks):** OpenRouter `nvidia/nemotron-3-ultra-550b-a55b:free`, `https://openrouter.ai/api/v1`, `ENV:openrouter_api_key`. Previously **resolved and verified**: Ollama, model `glm-5.3`, `https://ollama.com/v1`, credential `ENV:ollama_api_key`. The id is `glm-5.3` on the cloud endpoint and `glm-5.3:cloud` via the local daemon; the pairing is not interchangeable |
| Domain validation | Pydantic v2 |
| Canonical storage | SQLite; migrations; foreign keys; explicit transactions |
| Original evidence | Content-addressed local files, outside agent write access |
| Search | Metadata filtering plus SQLite FTS5 |
| Graph | Typed relational records; a small local visualization |
| Knowledge workspace | One-way Markdown/YAML export to Obsidian |
| Runtime | Official NousResearch/hermes-agent, pinned to an inspected commit |
| Model route | One verified route; no automatic provider substitution |
| Workflow | Researcher, clean-context critic, synthesis; bounded repair |
| Evolution | One offline configuration mutation; research-quality evaluation |
| Default tests | Offline, deterministic, no external network or model credentials |
| Live tests | Explicit opt-in, separately reported |

**Coding models and research models are separate choices.** Terra or GLM may build the application while Hermes uses another available tool-capable model. Do not hard-code a product dependency on a marketing model name or assume support for JSON/tool features.

### 1.3 Deferred scope

The v0.1 delivery excludes portfolio accounting, order proposals, broker integrations, return optimization, 50–100-stock screens, regime classification, and claims of investment alpha.

Also defer Neo4j, PostgreSQL extensions, Redis, MinIO, Prefect, Temporal, vector search, Next.js, Kubernetes, multi-provider routing, and an extensive telemetry stack. Add these only against measured requirements.

Retain the principles behind Sentinel as a small deterministic **research validator**, not a separate risk service.

### 1.4 Inputs to resolve in M0

**All resolved as of 20 September 2026 (amendment A1), except the EUR limit, which is deliberately not configurable.**

| Input | Resolution |
|---|---|
| Research model/provider, endpoint, credential | Ollama, `glm-5.3`, `https://ollama.com/v1`, `ENV:ollama_api_key`. Verified by live probe |
| Three companies and one theme | LULU, TSCO, CALX; theme *company guidance and demand changes*. Case mapping provisional until M2-T04 |
| Price source and permitted local use | Alpha Vantage `TIME_SERIES_DAILY`, `ENV:alpha_vantage_api_key`, free tier. Verified live for all three tickers. See 2.6 for the unadjusted-close caveat |
| Optional EUR spending limit | **Not configurable in v0.1.** Setting `limits.eur_cap` fails validation on purpose: with no cost reservation and no verified pricing, a hard cap cannot be honoured (3.8, row A22). Request, output and time limits apply and cost is reported as unknown |
| Desired demo date and weekly time | Still owner-supplied; does not block implementation |

Use fixtures to progress when credentials are absent. Mark live integration blocked; never replace a required live gate with a fake success.

---

## 2. Execution rules for smaller coding models

### 2.1 Work unit

Execute **one task card per coding session**. A milestone is a delivery gate, not one giant prompt.

- Target 1–3 implementation files plus 1 focused test file per task.
- Foundation tasks may create additional small metadata files listed explicitly.
- Split a task before editing if it exceeds this boundary or needs an unrelated refactor.
- Read only the relevant plan sections, current task, contracts, and directly related code/tests.
- Do not load the entire long-term blueprint by default.
- Do not implement future milestone features to make the current task easier.
- Do not invent upstream Hermes API arguments, commit IDs, model capabilities, or evaluation results.
- Do not silently change a frozen schema, CLI option, error code, or test expectation.
- Never weaken assertions, skip failing tests, or regenerate expected answers just to obtain a pass.
- Human-owned evidence annotations and evaluation labels are not coding-agent repair targets.
- A test that checks semantic behavior is preferred to a test that mirrors implementation details.

### 2.2 Dependency order

```text
M0 Foundation and Hermes feasibility
 -> M1 Contracts and epistemic rules
 -> M2 Evidence, snapshots, and storage
 -> M3 Bounded Hermes runtime
 -> M4 End-to-end research and CLI
 -> M5 Browser and Obsidian
 -> M6 Research-quality evolution experiment
 -> M7 Demo acceptance and packaging
```

Within a milestone, complete task cards in order. Each milestone requires the preceding milestone gate. Do not begin the next milestone while required checks are failing.

### 2.3 Reusable task prompt

```text
Implement task <TASK_ID> from EpisAlpha_MVP_Milestone_Implementation_Plan.md.

Read first:
- Sections 1–4 of the plan only where needed for this task.
- This task card and its milestone gate.
- docs/implementation/progress.md, if it exists during initial bootstrap.
- The listed input files and relevant existing tests.

Scope:
- Change only the listed files and directly necessary focused tests.
- Implement no later tasks.
- Preserve existing user work.
- Use the frozen contracts and exact command names.

Verification:
- Run the task's acceptance checks.
- Run lint/type checks relevant to changed code.
- Report actual commands, results, failures, and blocked prerequisites.
- Do not claim a live integration passed using a fake runtime.

Stop and report BLOCKED when an upstream interface is unverified,
credentials are missing for a required live check, a contract conflicts,
or scope requires an unapproved architectural change.

Finish with:
TASK_ID; files changed; behavior added; commands/results;
remaining risks; next eligible task.
```

### 2.4 Handoff record

Create `docs/implementation/progress.md` in M0. Keep one compact row per task:

| Field | Required content |
|---|---|
| Task | Stable ID, such as `M2-T02` |
| Status | `TODO`, `IN_PROGRESS`, `BLOCKED`, or `DONE` |
| Changes | File paths and one-sentence behavior summary |
| Verification | Exact command and actual result |
| Blocker | Missing input or failed check; not vague uncertainty |
| Next | Next eligible task ID |

A task is DONE only when its required acceptance checks pass. A milestone gate gets its own recorded result. Commits remain an explicit owner action; this plan does not authorize automatic commits or pushes.

### 2.5 Escalation rules

Ask the owner or request a stronger-model review when:

- Two bounded attempts fail to resolve the same issue.
- A schema or temporal rule needs changing.
- Hermes cannot expose the required trace, isolation, or model-call controls.
- A dependency conflicts with Python/runtime requirements.
- A financial assertion cannot be grounded in its cited passage.
- Evaluator behavior or human annotations appear inconsistent.

Provide a minimal reproducer and competing interpretations. Do not respond with a broad rewrite.

### 2.6 Verified provider constraints (amendment A3, A4, A6)

These were measured, not assumed. Build against them rather than against the advertised surface.

1. **`response_format` is accepted and silently ignored.** Both `json_schema` (`strict: true`) and
   `json_object` returned ordinary prose on this route — no error, no warning. Structured output
   **must** come from a forced `tool_choice` on a named function, whose arguments the host parses
   and validates. This is the concrete justification for the bounded repair in 3.6 step 7.
2. **Alpha Vantage free tier throttles harder than its published quota.** Nominally 25 requests
   per day and 5 per minute, but back-to-back requests are refused with an `Information` message
   advising roughly one request per second. A refusal returns HTTP 200 with no data, so the
   connector must treat an `Information` or `Note` key as `SOURCE_FAILED`, never as `NO_DATA`.
3. **The free-tier daily close is UNADJUSTED.** `TIME_SERIES_DAILY_ADJUSTED` is a premium
   endpoint. A split or dividend therefore produces a fake return in the raw series, which
   directly conflicts with the blueprint's adapter acceptance test that "splits and dividends do
   not create false returns". Until this is resolved, the price path must either carry an explicit
   unadjusted label wherever a return is shown, or source corporate actions separately. **Do not
   compute or display a multi-day return from the raw series without that label.**
4. **`glm-5.3` is a reasoning model.** Trivial prompts cost 600-1600 completion tokens, so the
   4 000-token per-call cap in 3.8 is workable but tight. Re-measure at M3-T02.

---

## 3. Architecture and contracts to freeze

### 3.1 Component responsibilities

```text
Browser / CLI
    -> application services and persisted jobs
    -> research runner
         -> snapshot-bound tools
         -> isolated Hermes worker
         -> single-route model relay
    -> deterministic validation
    -> canonical records and run artifacts
         -> evidence/relationship views
         -> Obsidian export
         -> offline evaluation reports
```

- **Application services:** own jobs, idempotency, snapshots, state transitions, and persistence.
- **Connectors:** fetch allowlisted sources and record source metadata; never infer investment conclusions.
- **Evidence services:** preserve payloads, deterministic text extraction, passages, and document versions.
- **Hermes worker:** reads a frozen snapshot through typed tools and returns candidate research.
- **Model relay:** forwards only the selected provider/model API calls and accounts for requests/usage.
- **Validator:** checks schema, reference integrity, temporal eligibility, required sections, and deterministic calculations.
- **Evaluator:** reads completed artifacts and protected case labels; does not execute candidate code.
- **Exporters:** create derived representations; never become canonical storage.

SQLite uses WAL mode, foreign keys, a busy timeout, and short transactions. WAL does not create multiple simultaneous writers. Limit v0.1 to one active research job; browser reads and job-admission writes remain short.

### 3.2 Minimum domain objects

All IDs are application-generated, stable, filesystem-safe identifiers. User titles and model text are never filesystem paths. All timestamps are timezone-aware UTC; serialize with explicit offsets. Values for money or financial measurements use decimal strings plus units, not uncontrolled binary floating-point conversion.

| Contract | Minimum content |
|---|---|
| `Entity` | `entity_id`, kind, canonical name, aliases, external identifiers |
| `Instrument` | `instrument_id`, issuer entity ID, exchange, currency, dated ticker aliases |
| `EvidenceDocument` | ID, source URI/type, payload hash, parsed-text hash, parser version, publication/public-availability metadata, actual ingestion time, source-family ID, revision predecessor |
| `EvidenceSpan` | ID, document ID, normalized-text start/end offsets, exact quote, optional section locator |
| `Claim` | ID, atomic statement, subject IDs, attribution, epistemic status, span references or deterministic derivation, semantic review status, actual creation time, run ID |
| `Event` | ID, event type, participating entities, economic time/period, supporting claim IDs |
| `Hypothesis` | ID, mechanism, assumptions, supporting/opposing claim IDs, falsification condition, horizon |
| `Relation` | ID, source/target IDs, allowed predicate, evidence/derivation references, temporal scope, epistemic status, creator/run |
| `ThesisAssertion` | ID, section, text, nonempty claim and/or hypothesis references |
| `Thesis` | ID, instrument ID, research cutoff, horizon, stance, assertion list, missing information, next inquiry, model/harness/snapshot versions |
| `SnapshotManifest` | ID/hash, instrument IDs, research cutoff, evidence versions, permitted spans/claims/relations, market context, input hashes, source/ontology versions |
| `RunRequest` | ID/idempotency key, instrument ID, question, cutoff, research mode, runtime mode (`fake` or `hermes`), harness ID, budgets |
| `RunRecord` | Request, state, stage checkpoints, warnings/errors, artifacts, versions, usage, actual start/end times |
| `ValidationReport` | Structural validity, individual check results, unresolved semantic reviews, warnings, terminal disposition |
| `SemanticAssessment` | ID, claim/relation ID, judgment, rationale, reviewer type/identity, actual assessment time, superseded assessment ID |
| `RuntimeContext` | Frozen snapshot, validated current-run intermediate records, stage, remaining budget, run-scoped authorization |
| `StageResult` | Stage, candidate structured payload, completion/exit reason, tool events/result hashes, usage, actual timestamps |

Subtypes for numeric claims must preserve metric, value, unit, period, accounting basis, and source context. Missing dimensions remain explicit rather than guessed.

**User-visible material research statements must use `ThesisAssertion`.** Do not add an unrestricted summary field that bypasses assertion references. Render narrative sections from structured assertions.

The input snapshot is immutable. Newly generated claims/hypotheses belong to a separate current-run record set: the host validates them, assigns canonical IDs, and passes accepted records to later stages through `RuntimeContext`. They may cite only eligible source spans or already validated current-run records. This permits synthesis without pretending the newly computed claims existed in the historical input snapshot. Final artifacts preserve both input manifest and generated records. Candidate-local IDs are mapped by the host; models cannot overwrite an existing canonical ID.

### 3.3 Controlled vocabulary

Freeze these initially:

```text
epistemic_status:
  reported | derived | hypothesized

semantic_review_status:
  unreviewed | supported | partially_supported | unsupported

research_stance:
  investigate | watch | abstain

thesis_section:
  observation | interpretation | expectation | variant_view |
  transmission | bull_case | bear_case | invalidation

relation_predicate:
  ISSUED_BY | HAS_SPAN | REPORTS | ABOUT | SUPPORTS |
  CONTRADICTS | DERIVED_FROM

research_mode:
  forward_research | historical_reconstruction

source_family:                       # amendment A2
  market | news | social | fundamentals | macro

provenance_strength:                 # amendment A2
  primary | secondary | unverified
```

`provenance_strength` is **not** a quality score. It records what kind of thing a source is:
`primary` is the issuer's or regulator's own document, `secondary` is a report *about* a primary
source, and `unverified` is public commentary with no availability guarantee and no accountable
publisher. The filings source must be `primary` — a report about a filing is not the filing.

`reported` means a source made the assertion, not that the world necessarily matches it. `derived` requires input references and a versioned deterministic calculation. `hypothesized` requires explicit assumptions and does not become a fact by repetition.

A clean citation and valid schema do not automatically change semantic review to `supported`. Human review, or a clearly identified secondary assessor, supplies that assessment and its provenance.

Store semantic assessments as versioned records rather than overwriting historical judgments. The assessment presented in a run must be the one captured in that run's manifest/artifacts.

### 3.4 Relationship constraints

| Predicate | Allowed source | Allowed target |
|---|---|---|
| `ISSUED_BY` | Instrument | Entity |
| `HAS_SPAN` | EvidenceDocument | EvidenceSpan |
| `REPORTS` | EvidenceSpan | Claim |
| `ABOUT` | Claim | Entity, Instrument, Event |
| `SUPPORTS` | Claim | Hypothesis, Thesis |
| `CONTRADICTS` | Claim | Claim, Hypothesis, Thesis |
| `DERIVED_FROM` | Thesis | Earlier Thesis |

Reject unknown predicates, missing endpoints, invalid source/target types, and self-relations. Do not infer `CONTRADICTS` merely from different numeric values: subject, period, units, and accounting scope must be compatible, and the assessment must be recorded.

No `CAUSES` relation in v0.1. Hypothesis mechanisms remain explicit text attached to supporting/opposing claims.

**Unverified sources cannot carry an assertion alone (amendment A2).** A claim whose only
supporting spans come from `unverified` sources may not be the sole support for a
`ThesisAssertion`. The validator must enforce this, and social sources stay disabled in
configuration until it does. An unverified source can raise a question; it cannot settle one.

**Numbers are reported or recomputed, never asserted (amendment A8).** Every number a
`ThesisAssertion` relies on comes from a `NumericFact` on either a `reported` claim with a cited
span, or a `derived` claim whose `Derivation` names a registered `method`@`method_version` and
whose value the validator recomputes from the input claims' `NumericFact`s. A mismatch, an
unknown method, or incompatible input units/periods fails validation. The model may propose a
derivation; it never supplies the computed value.

### 3.5 Temporal rules

Do not collapse these clocks:

- Economic event time or reporting period.
- Source publication time.
- When the exact source version became publicly available.
- When EpisAlpha actually captured or created a record.
- Research cutoff.
- Actual execution time of the research run.

Each document has `public_available_at` (nullable), `availability_basis`, and `ingested_at`.

```text
availability_basis:
  provider_verified | archive_verified | first_capture | unknown
```

Eligibility rules:

1. A verified public-availability time can qualify that exact version for historical reconstruction.
2. If public availability cannot be verified, use actual first capture as conservative eligibility time and label the basis `first_capture`.
3. A publication date alone never proves that today's fetched version existed at that historical date.
4. Unresolved availability metadata cannot qualify a document for an earlier cutoff.
5. Forward runs also require actual capture before the frozen cutoff. Freeze only after collecting the intended input set, or exclude late arrivals.
6. Retain older document versions. Select the latest qualifying version as of the cutoff, not today's latest and not invariably the first-reported version.
7. Build graph views from the manifest's eligible records. A current graph cannot be injected into a past run.
8. A claim created today from older evidence keeps today's `created_at`. Its evidence cutoff is separate; do not backdate creation.
9. Prior theses, semantic assessments, and outcome lessons are unavailable to earlier runs unless their actual creation/availability qualifies.
10. Tool handlers obtain cutoff and snapshot from immutable run context. Agent-supplied dates cannot expand access.

Historical reconstruction must display: **“Retrospective research; model training knowledge may include later events.”** Point-in-time retrieval is not a guarantee against model-weight hindsight.

### 3.6 Research workflow and states

Stages:

1. Validate request and admit idempotently.
2. Freeze eligible evidence and market context.
3. Researcher produces claims and candidate hypotheses.
4. Validate references before passing them to later stages.
5. Critic checks counter-evidence and missing information in a fresh context.
6. Synthesizer creates `Thesis` from validated intermediate records.
7. Run deterministic validation; allow one bounded schema/reference repair. **This step is load-bearing, not defensive decoration (amendment A3):** the provider ignores `response_format`, so the host is the only thing that enforces structure. Validation includes recomputing every derived numeric value (amendment A8).
8. Persist completed research, abstention, partial result, or explicit failure.

```text
QUEUED -> SNAPSHOT_FROZEN -> RESEARCHING -> CRITIQUING
       -> SYNTHESIZING -> VALIDATING
       -> RESEARCH_COMPLETED | ABSTAINED | PARTIAL | REJECTED

SNAPSHOT_FROZEN -> ABSTAINED: essential evidence missing
Any active research stage -> VALIDATING: early candidate rejection or partial-result review
Any nonterminal state -> FAILED | CANCELLED | TIMED_OUT
```

All terminal states include reason, warnings, usage, and artifact references. `PARTIAL` is visibly non-complete. Missing essential evidence produces `ABSTAINED`; invalid candidate references that cannot be repaired produce `REJECTED`.

Network failures after partial work must preserve that work while recording failed/incomplete status. Never silently translate a provider outage into a valid abstention.

**Background execution:** Both entry points use shared admission and worker services. Browser submission persists a job and launches a dedicated trusted runner subprocess once; page reruns only read status. The internal `research execute RUN_ID` command atomically claims that job, drives the isolated Hermes worker, and persists progress. The CLI `research run` uses the same path and waits for terminal status. Persist cancellation requests; the runner watchdog observes them independently of the browser. A second worker cannot claim the same job, and a stale worker lease requires explicit recovery. This is a local process pattern, not a distributed queue.

### 3.7 Replay and reproducibility

- **Saved artifact replay:** opens recorded tool results, model outputs, thesis, assessments, and manifests. Makes zero model/network calls; historical content remains unchanged.
- **Fresh inference:** creates a new run against a specified frozen snapshot. May produce different results. Links to prior run rather than overwriting it.
- **Recovery:** resumes deterministic completed stages. An interrupted model stage is recorded as incomplete; explicitly restart it as a new attempt, preserving old attempt metadata.

Persist before declaring success. Snapshot hash, harness hash, ontology/schema version, runtime commit, provider/model identifier, model parameters, parser version, and evaluator hash are recorded when applicable.

### 3.8 Initial limits

Defaults are proposed engineering limits, not measured performance:

| Limit | Default | Enforcement |
|---|---:|---|
| Active research jobs | 1 | Application admission |
| Run wall time | 300 seconds | Parent worker watchdog |
| Model HTTP requests | 8 total, including retries/auxiliary calls | Single-route relay |
| Tool calls | 12 total | Tool adapter |
| Response output-token request cap | 4,000 per call, using verified provider field | Relay/provider adapter |
| Model request body | 128 KiB per request | Relay |
| Individual tool result | 32 KiB | Tool adapter |
| Evidence search hits | 6 per call | Tool handler |
| Candidate output repair | 1 | Workflow |
| Transport retry | 1 for explicitly transient failures | Provider adapter; counts toward request budget |
| Source requests per day | 25 for `alpha_vantage` (shared with `alpha_vantage_news`) | Connector; amendment A4 |
| Source request spacing | ≥ 1 second between calls to the same source | Connector; amendment A4 |

Actual tokens/cost are reported from provider usage and versioned pricing where available. Unknown usage or pricing stays unknown. Do not claim a hard EUR cap unless conservative reservation and pricing support are implemented and tested; if the owner requires such a cap and support is absent, block live runs.

Keep numerical limits in one validated settings object, not scattered magic numbers. Cancellation must terminate the worker and its child processes and close requests within a tested deadline.

---

## 4. Repository shape and verification conventions

### 4.1 Target structure

Create directories only when their first task needs them.

```text
EpisAlpha/
├── EpisAlpha_Architecture_and_Implementation_Blueprint.md
├── EpisAlpha_MVP_Milestone_Implementation_Plan.md
├── README.md
├── pyproject.toml
├── uv.lock
├── .gitignore
├── config/
│   ├── demo.example.toml
│   └── runtime.lock.json
├── src/episalpha/
│   ├── __init__.py
│   ├── settings.py
│   ├── cli.py
│   ├── contracts/
│   │   ├── knowledge.py
│   │   ├── research.py
│   │   └── errors.py
│   ├── storage/
│   │   ├── db.py
│   │   ├── repository.py
│   │   ├── objects.py
│   │   └── migrations/001_initial.sql
│   ├── evidence/
│   │   ├── parsing.py
│   │   ├── temporal.py
│   │   └── snapshots.py
│   ├── connectors/
│   │   ├── filings.py
│   │   ├── prices.py
│   │   └── xbrl.py
│   ├── runtime/
│   │   ├── port.py
│   │   ├── fake.py
│   │   ├── hermes.py
│   │   ├── tools.py
│   │   ├── model_relay.py
│   │   └── sandbox.py
│   ├── research/
│   │   ├── runner.py
│   │   ├── validation.py
│   │   ├── derivations.py
│   │   └── artifacts.py
│   ├── knowledge/
│   │   ├── query.py
│   │   └── export_obsidian.py
│   ├── evaluation/
│   │   ├── cases.py
│   │   ├── scoring.py
│   │   └── reporting.py
│   └── evolution/
│       ├── candidates.py
│       └── campaign.py
├── apps/streamlit_app.py
├── harnesses/baseline/
│   ├── researcher.md
│   ├── critic.md
│   ├── synthesizer.md
│   └── config.json
├── scripts/
│   ├── probe_hermes.py
│   └── demo_smoke.py
├── runtime/
│   ├── Dockerfile
│   └── compose.yaml
├── tests/
│   ├── conftest.py             # amendment A7: makes tests/fixtures importable everywhere
│   ├── contracts/
│   ├── evidence/
│   ├── runtime/
│   ├── research/
│   ├── ui/
│   ├── knowledge/
│   ├── evaluation/
│   ├── evolution/
│   ├── integration/
│   └── fixtures/
├── eval_cases/
│   ├── manifests/
│   └── development/
├── docs/implementation/
│   ├── progress.md
│   ├── hermes_probe.md
│   ├── demo_acceptance.md
│   └── demo_script.md
└── .episalpha/                 # Local runtime state; ignored by Git
    ├── app.sqlite3
    ├── objects/
    ├── snapshots/
    ├── runs/
    ├── exports/
    └── candidates/
```

Validation/holdout labels live outside the agent-accessible workspace, configured by an evaluator-only path. They are not placed under the Hermes mounted snapshot or the candidate optimizer's inputs.

### 4.2 Minimal dependency policy

- Runtime application: Pydantic, Typer, HTTPX, Streamlit; add small parsing/visualization dependencies only at the relevant task.
- Standard library SQLite for initial persistence; no ORM requirement.
- Development: pytest, Ruff, mypy; lock resolved versions with `uv`.
- Hermes dependencies live in the pinned runtime environment/container, never in the application environment. Hermes exact-pins its own dependencies, so sharing a virtualenv would fight the application's lock.
- **Hermes cannot be installed as a built wheel (amendment A5).** Its `setup.py` deliberately raises `RuntimeError: Building wheels or sdists for hermes-agent is not supported. Hermes is distributed via the shell installer, Docker image, or Nix.` A `pip install git+https://...` therefore fails. Supported paths: the shell installer, the Docker image, Nix, or `uv pip install -e .` from a clone at the pinned commit. **Use the Docker image for the M3 runtime** — it is upstream's supported distribution and already provides the isolation this plan requires.
- Do not install every Hermes optional extra unless the integration spike proves it necessary.
- No new framework without a concrete task requirement.

### 4.3 Test commands

These are **target commands to implement**, not commands already available in this repository.

Every completed milestone runs:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src/episalpha
uv run pytest -q -m "not live"
```

Register `live` in pytest configuration. Offline tests must block external network and work without credentials. Explicit test fixtures may allow only their loopback fake-provider endpoint. Default tests may use `FakeRuntime`, but its outputs must be explicitly labeled fixtures.

Type-check owned code; isolate untyped Hermes imports inside its adapter. Do not globally disable typing to accommodate an upstream package.

---

## 5. Milestone overview

Estimates are focused engineering days, including review and normal fixes. Small-model integration failures or unfamiliar source parsing can extend them. They do not measure time required to establish financial predictive value.

| Milestone | Deliverable | Estimate | Gate |
|---|---|---:|---|
| M0 | Build skeleton and verified Hermes feasibility | 1–2 days | G0 |
| M1 | Frozen contracts and invariants | 1–2 days | G1 |
| M2 | Evidence store, temporal snapshots, fixtures | 2–3 days | G2 |
| M3 | Bounded, isolated Hermes research runtime | 2–3 days | G3 |
| M4 | Working research CLI and artifact replay | 1–2 days | G4 |
| M5 | Browser workbench and Obsidian export | 2 days | G5 |
| M6 | One research-quality evolution campaign | 2 days | G6 |
| M7 | Demo acceptance, recovery, documentation | 1–2 days | G7 |
| **Total** | **Local research-workbench MVP** | **12–18 days** | **All gates** |

Earliest user-visible review: M4 CLI. First browser demonstration: M5. Full requested demo, including measured harness comparison: M7.

---

## 6. M0 — Foundation and integration feasibility

**Goal:** Establish a runnable project and verify the risky external integration before building around imagined capabilities.

### M0-T01 — Bootstrap owned application

- **Depends on:** Nothing.
- **Files:** `pyproject.toml`, `src/episalpha/__init__.py`, `src/episalpha/cli.py`, `.gitignore`; generated `uv.lock`.
- **Build:** Python package, `episalpha` console entry point, `--version`, test/lint/type configuration, registered `live` marker, Git exclusions for runtime state and secrets.
- **Acceptance:** Editable install succeeds; `uv run episalpha --version` prints a version; Ruff and mypy accept the skeleton; a packaging smoke test imports the package.
- **Focused test:** `tests/integration/test_package.py`.
- **Stop:** Package metadata and entry point exist; no product commands yet.

### M0-T02 — Resolve settings and record execution state

- **Depends on:** M0-T01.
- **Files:** `src/episalpha/settings.py`, `config/demo.example.toml`, `docs/implementation/progress.md`, `README.md`.
- **Build:** Validated settings for local paths, selected companies/theme, source IDs, provider route, and section 3.8 limits. Credentials are environment references, never literal values in tracked config.
- **Acceptance:** Invalid limits and unknown fields fail with actionable messages; relative paths resolve from explicit project/data root; loading config does not initiate network calls; README explains offline setup.
- **Focused test:** `tests/contracts/test_settings.py`.
- **Owner checkpoint:** Record unresolved provider/source choices as BLOCKED, while allowing offline development.

### M0-T03 — Probe official Hermes and one model route

- **Depends on:** M0-T02.
- **Files:** `scripts/probe_hermes.py`, `config/runtime.lock.json`, `docs/implementation/hermes_probe.md`.
- **Build:** Disposable minimal integration probe against official upstream. Record exact inspected commit, install approach, Python compatibility, supported entry point, and actual configuration keys.
- **Probe:** One typed read-only synthetic tool, fresh profile, tool allowlist, structured final output, tool trace, usage reporting, cancellation, and main/auxiliary model routing.
- **Acceptance:** A real selected-model call uses the intended tool and returns a parseable result. Report exactly which controls are available, absent, or require the relay/parent worker. Trace records actual upstream commit and model ID.
- **Focused test:** `tests/integration/test_hermes_probe.py`, marked `live`.
- **Stop:** Do not implement an elaborate runtime. If required control is impossible, resolve adapter approach now rather than fabricating an API.
- **Outcome (amendment A5, completed 20 September 2026).** Commit `c1488ac947c9bc33fd65ec464548dc9d8edd6122`, version `0.21.3`, MIT. Controls present on `run_agent.AIAgent`: `enabled_toolsets`/`disabled_toolsets`, `skip_memory`, `skip_context_files`, `load_soul_identity`, `session_id`, `max_iterations`, `iteration_budget`, `max_tokens`, `event_callback`, `interrupt()`/`clear_interrupt()`/`close()`, `get_activity_summary()`, `base_url`/`api_key`/`provider`/`api_mode`/`model`. `fallback_model` and `providers_*` exist and **must stay unset** — 1.2 forbids automatic substitution.
- **Open item carried into M3.** There is **no in-process tool injection**: `AIAgent.__init__` exposes none of `mcp_servers`, `tools`, `extra_tools`, `custom_tools`, `tool_registry`, and `toolsets.create_custom_toolset(name, description, tools, includes)` composes existing tool *names* only. EpisAlpha's typed tools must reach Hermes over **MCP**, which is file-configured (`mcp.json` under `$HERMES_HOME`/`~/.hermes`); MCP tools surface with an `mcp_` prefix that `create_custom_toolset` can then allowlist. This path is evidence-backed but **unproven end to end** — M3-T01 must demonstrate it before the runtime is built on it.

### Gate G0

```bash
uv run episalpha --version
uv run pytest -q tests/contracts/test_settings.py tests/integration/test_package.py
uv run pytest -q -m live tests/integration/test_hermes_probe.py
```

Also run section 4.3 checks. Owner reviews probe findings and selected provider/source. G0 remains blocked if live feasibility is unverified; offline scaffolding may be prepared, but later live gates cannot be declared passed.

---

## 7. M1 — Canonical contracts and epistemic invariants

**Goal:** Eliminate ambiguity before database and agent code diverge.

### M1-T01 — Knowledge contracts

- **Depends on:** G0.
- **Files:** `src/episalpha/contracts/knowledge.py` and contract fixtures.
- **Build:** Entity, Instrument, EvidenceDocument, EvidenceSpan, Claim, Event, Hypothesis, Relation, SemanticAssessment; exact controlled vocabularies and typed reference rules.
- **Acceptance:** Naive timestamps, unsupported statuses, malformed identifiers, missing claim provenance, inconsistent span ranges, and numeric facts without required context are rejected. Hypotheses require assumptions and falsification conditions.
- **Focused test:** `tests/contracts/test_knowledge.py`.
- **Fixture:** One synthetic document, two passages, a reported claim, a contradictory claim, and one hypothesis. Clearly label all as synthetic.

### M1-T02 — Research contracts, lifecycle, and errors

- **Depends on:** M1-T01.
- **Files:** `src/episalpha/contracts/research.py`, `src/episalpha/contracts/errors.py`; read frozen knowledge contracts without redefining them.
- **Build:** RunRequest, SnapshotManifest, ThesisAssertion, Thesis, RunRecord, ValidationReport, RuntimeContext, StageResult; state-transition validator. Reference SemanticAssessment from the knowledge contracts established in M1-T01.
- **Error codes:** `NO_DATA`, `SOURCE_FAILED`, `INVALID_REQUEST`, `INVALID_OUTPUT`, `INELIGIBLE_EVIDENCE`, `BUDGET_EXCEEDED`, `NOT_AUTHORIZED`, `INTEGRITY_ERROR`.
- **Acceptance:** Invalid transitions fail; terminal records require reasons; material assertions require claim/hypothesis references; missing information is distinct from source failure; retrospective mode carries its limitation label.
- **Focused test:** `tests/contracts/test_research.py`.

### M1-T03 — Temporal eligibility policy

- **Depends on:** M1-T02.
- **Files:** `src/episalpha/evidence/temporal.py`, temporal fixtures.
- **Build:** Pure functions implementing section 3.5, with explicit comparison behavior at cutoff boundaries.
- **Acceptance:** Reject future documents, unverified historical versions, and retrospective lessons; include exactly-at-cutoff eligible versions; preserve actual creation time for reconstructed analysis; select correct document revision for each cutoff.
- **Focused test:** `tests/evidence/test_temporal.py`.
- **Key fixture:** Version A available at T1; corrected version B at T3; a T2 query returns A even after B is ingested.

### M1-T04 — Structural evidence and graph validator

- **Depends on:** M1-T03.
- **Files:** `src/episalpha/research/validation.py`.
- **Build:** Reference resolution, relation endpoint/type checks, assertion coverage, exact quotation/offset checks, and deterministic derivation verification.
- **Acceptance:** Missing/mismatched citations fail; invalid relation types fail; unsupported hypotheses cannot be relabeled reported; quotation matching never claims semantic entailment; semantic status stays unreviewed unless an assessment exists.
- **Focused test:** `tests/research/test_validation.py`.

### M1-T05 — Derivation registry and recomputation (amendment A8)

- **Depends on:** G1.
- **Files:** `src/episalpha/research/derivations.py` (new), `src/episalpha/research/validation.py` (add `check_derivations`, wire into `validate()`).
- **Build:** A frozen registry mapping `method` + `method_version` to pure `Decimal` functions: `difference`, `pct_change`, `ratio`, `margin`, `range_midpoint` (guidance range), `guidance_revision` (new midpoint vs prior midpoint). One explicit quantize/rounding rule. Unit and period compatibility checks on inputs. The validator recomputes each `derived` claim's `numeric_fact.value` from its input claims' `NumericFact`s.
- **Acceptance:** Unknown method or version fails with a typed error; recomputed value differing from the claimed value fails; mismatched units/periods fail; division by zero is an error, never `0`; no floats anywhere. Closes the gap where M1-T04 resolved derivation inputs but never recomputed the value.
- **Schema:** None. Uses existing `Derivation` and `NumericFact` fields; `SCHEMA_VERSION` stays `1`.
- **Focused test:** `tests/research/test_derivations.py`.

### Gate G1

```bash
uv run pytest -q tests/contracts tests/evidence/test_temporal.py tests/research/test_validation.py
```

Also run section 4.3 checks. Owner reviews representative serialized examples. Freeze schema version `1`; future contract changes require an explicit migration/compatibility decision.

---

## 8. M2 — Evidence storage, connectors, and snapshots

**Goal:** Produce source-linked, immutable-in-practice inputs before asking Hermes to reason over them.

### M2-T01 — SQLite persistence and migration

- **Depends on:** G1.
- **Files:** `src/episalpha/storage/db.py`, `src/episalpha/storage/repository.py`, `src/episalpha/storage/migrations/001_initial.sql`.
- **Build:** Record tables, typed relations, versioned assessments, runs/attempts, stage checkpoints, usage, and FTS5 index. Add foreign-key/uniqueness constraints and explicit transaction boundaries. Use a shared typed-node registry for relationship endpoint foreign keys; enforce permitted source/target kinds in the validator. Do not simulate cross-table foreign keys with unchecked string IDs.
- **Acceptance:** Migration works on an empty database and is idempotent; transaction rollback leaves no half-written thesis; duplicate idempotency keys do not create duplicate runs; relationship endpoints cannot dangle.
- **Focused test:** `tests/evidence/test_repository.py`.
- **Implementation rule:** Do not use a single opaque JSON blob as the only graph/research store. JSON payload columns may accompany queryable IDs, types, versions, and timestamps.

### M2-T02 — Content-addressed payloads and exact spans

- **Depends on:** M2-T01.
- **Files:** `src/episalpha/storage/objects.py`, `src/episalpha/evidence/parsing.py`.
- **Build:** SHA-256 addressed original bytes; deterministic normalized text; parser/text hashes; exact spans into normalized text; atomic writes without replacement of existing different content.
- **Acceptance:** Same bytes deduplicate; changed bytes create new objects; hash mismatch fails; quote equals text slice; active HTML content is removed from rendered text; original payload remains retrievable by hash.
- **Focused test:** `tests/evidence/test_objects_and_spans.py`.
- **Scope:** HTML/plain text first. PDF/OCR parsing is not required for the selected demo corpus.

### M2-T03 — Narrow source adapters

- **Depends on:** M2-T02.
- **Files:** `src/episalpha/connectors/filings.py`, `src/episalpha/connectors/prices.py`, connector response fixtures.
- **Build:** Import preserved SEC/IR payloads and enable explicit allowlisted fetching; price-context adapter for the selected source. Use stable issuer/instrument identifiers and source-specific timestamp semantics.
- **Acceptance:** Recorded fixtures ingest without network; source failures remain `SOURCE_FAILED`; missing data is `NO_DATA`; current data cannot silently substitute for a historical request; prices carry currency, date, adjustment basis, and source.
- **Focused test:** `tests/evidence/test_connectors.py`.
- **SEC rules:** Identify client with appropriate User-Agent; cache; stay below current fair-access limits; distinguish filing date, acceptance, and verified dissemination/availability.
- **Price rule:** Display context only in v0.1. Do not turn an uncertain adjusted-price series into verified investment returns.
- **Amended source set (A2).** Implement `sec_edgar` (filings, primary) and `alpha_vantage` (daily price, primary) first; `alpha_vantage_news` (secondary) next. `fred`, `reddit` and `stocktwits` are configured but disabled and must stay disabled until the validator enforces the unverified-source rule in 3.4.
- **Amended acceptance (A4, A6).** An `Information` or `Note` key in an Alpha Vantage HTTP 200 response is a throttle or entitlement refusal and maps to `SOURCE_FAILED`, never `NO_DATA`. Space same-source requests at least one second apart and respect the 25/day budget shared with `alpha_vantage_news`. The free-tier close is unadjusted, so any stored price series records that fact and no multi-day return is shown without it. SEC EDGAR requires a descriptive User-Agent carrying contact details.

### M2-T04 — Frozen snapshot builder and demo corpus

- **Depends on:** M2-T03.
- **Files:** `src/episalpha/evidence/snapshots.py`, three fixture manifests, curated source metadata.
- **Build:** Snapshot assembly from eligible records; deterministic serialization/hash; explicit source completeness; snapshot-scoped search inputs. Add three curated demo cases and small synthetic adversarial variants.
- **Acceptance:** Later ingestion cannot alter an existing snapshot; outside-snapshot IDs are rejected; copied source material shares source-family lineage; absent essential evidence remains visible; changing cutoff changes eligibility correctly.
- **Focused test:** `tests/evidence/test_snapshots.py`.
- **Owner checkpoint:** Confirm source permissions and manually inspect key quotations in the three real demonstration cases. Synthetic cases are visibly separate.

### M2-T05 — Point-in-time XBRL fundamentals (amendment A8)

- **Depends on:** M2-T03, M1-T05.
- **Files:** `src/episalpha/connectors/xbrl.py` (new; reuse `user_agent`/`check_allowed` from `connectors/filings.py`), `tests/fixtures/connectors/companyfacts_*.json`.
- **Build:** Parse SEC `companyfacts` into `NumericFact` candidates carrying concept, unit, period, form, accession and `filed`. Select the latest fact with `filed <= cutoff` per concept, period and unit, reusing `evidence/temporal.py` where semantics match. Store the raw payload content-addressed so each fact cites an exact span.
- **Acceptance:** A restatement filed after the cutoff is never selected; the `frames` API is never called; a refusal maps to `SOURCE_FAILED` and missing data to `NO_DATA`; injected transport keeps the default suite offline.
- **Focused test:** `tests/evidence/test_xbrl.py`.

### Gate G2

```bash
uv run pytest -q tests/evidence
```

Also run section 4.3 checks. For each demo case, a reviewer can open raw source bytes, normalized text, selected spans, and exact snapshot manifest. Include one future-source rejection and one source-failure case.

---

## 9. M3 — Bounded Hermes runtime

**Goal:** Real Hermes produces traceable candidate outputs while canonical evidence and evaluation remain outside its authority.

### M3-T01 — Runtime port, fake runtime, and typed tools

> **Amendment A5.** Typed tools reach Hermes as an **external MCP server**, not as in-process callables — see the M0-T03 outcome. First task here is to prove that path with a minimal MCP server and one read-only tool, before any EpisAlpha tool surface is designed around it. Run Hermes from its **Docker image**.


- **Depends on:** G2, M2-T05 (amendment A8).
- **Files:** `src/episalpha/runtime/port.py`, `src/episalpha/runtime/fake.py`, `src/episalpha/runtime/tools.py`.
- **Build:** `ResearchRuntimePort.run_stage(stage, context) -> StageResult`; cancellation contract; deterministic fake; typed read-only tools:
  - `resolve_instrument`
  - `search_evidence`
  - `get_evidence_span`
  - `get_market_context`
  - `get_support_and_contradictions`
  - `get_numeric_facts` (amendment A8; snapshot-bound XBRL/reported facts)
  - `compute_derivation` (amendment A8; the host computes a registered method over validated input claims and returns value plus `method_version` — the model only proposes the call)
- **Acceptance:** Every tool is bound to snapshot/cutoff, enforces limits, returns typed errors, and records result hashes. Arbitrary SQL, URLs, filesystem paths, or broader cutoffs cannot expand access. Fake output includes fixture provenance.
- **Focused test:** `tests/runtime/test_tools.py`.

### M3-T02 — Single-route model relay

> **Amendment A3.** The relay must **not** send `response_format`. This route accepts it and silently returns prose. Structured output comes from a forced `tool_choice` on a named function whose arguments the relay parses and validates; a test must assert that the ignored-`response_format` behaviour is still what it was, so a provider change is noticed rather than assumed.


- **Depends on:** M3-T01.
- **Files:** `src/episalpha/runtime/model_relay.py`, `src/episalpha/settings.py` only if required by verified probe.
- **Build:** Minimal adapter/relay for the API surface confirmed in M0. Route every main and auxiliary model request to one approved provider/model; inject provider credentials only in trusted relay; validate per-run short-lived token; count requests/retries and available usage.
- **Acceptance:** Unknown routes/models fail closed; request-size/output/request-count caps apply; missing usage is explicit; secrets are redacted; retries count; cancellation closes requests; budgets are not reset by a new stage or worker retry.
- **Focused test:** `tests/runtime/test_model_relay.py` using a local fake provider.
- **Scope:** Implement only the endpoint/features actually used by the pinned Hermes path. No general-purpose model gateway, routing optimization, or invented OpenAI compatibility.

### M3-T03 — Hermes adapter and frozen research harness

- **Depends on:** M3-T02.
- **Files:** `src/episalpha/runtime/hermes.py`, `harnesses/baseline/researcher.md`, `critic.md`, `synthesizer.md`, `config.json`.
- **Build:** Pinned integration using probe-verified API; registered/filtered tools; fresh stage contexts; candidate JSON output; tool/model traces; read-only harness configuration. The prompt files are short assets, not extra application modules.
- **Acceptance:** Real workflow cites fixture span IDs, preserves unknowns, and produces parseable stage outputs. Critic receives validated claims plus eligible evidence, not uncontrolled conversational memory. Malformed output is returned as error, not quietly accepted.
- **Focused tests:** `tests/runtime/test_hermes_adapter.py` offline protocol tests; `tests/integration/test_hermes_runtime.py` marked `live`.
- **Rule:** Disable personal memory, session recall, automatic skill mutation, delegation, shell, browser, generic file access, and unrelated plugins for research execution. Verify actual effective tool list against an allowlist.

### M3-T04 — Whole-worker isolation and watchdog

- **Depends on:** M3-T03.
- **Files:** `src/episalpha/runtime/sandbox.py`, `runtime/Dockerfile`, `runtime/compose.yaml`.
- **Build:** Containerize the entire Hermes worker, not merely its terminal backend. Mount only frozen snapshot/harness read-only and a per-run output directory read-write. Do not mount repository, canonical SQLite, evaluator labels, or provider credentials.
- **Network:** Agent runs on an internal network reaching only the trusted model relay; relay has separately controlled provider access. Read-only tools operate on the mounted frozen snapshot. If the chosen transport differs, prove equivalent access constraints before claiming the gate.
- **Acceptance:** Worker cannot change evidence/harness or read hidden labels; no Docker socket is mounted; unrelated outbound connection fails; timeout/cancel terminates child processes; partial output is retained but never marked complete.
- **Focused test:** `tests/integration/test_runtime_boundary.py`, opt-in `live` because Docker is required; provider can be fake for boundary checks.
- **Stop:** Do not add Kubernetes, secrets platforms, or arbitrary sandbox backends.

### Gate G3

```bash
uv run pytest -q tests/runtime
uv run pytest -q -m live tests/integration/test_hermes_runtime.py tests/integration/test_runtime_boundary.py
```

Also run section 4.3 checks. Record effective tools, model route, runtime/harness hashes, observed budget enforcement, and measured cancellation behavior. At least one real-provider run is required; Docker boundary checks alone do not establish model compatibility.

---

## 10. M4 — End-to-end research, CLI, and replay

**Goal:** Deliver a complete vertical slice before UI work.

### M4-T01 — Research runner and job lifecycle

- **Depends on:** G3.
- **Files:** `src/episalpha/research/runner.py`, `src/episalpha/research/artifacts.py`.
- **Build:** Section 3.6 stages and background-worker lifecycle, persisted transitions/checkpoints, one-job admission, atomic worker claims/cancellation flags, runtime selection, validation boundary, one bounded repair, artifacts, and terminal reasons.
- **Acceptance:** Fake runtime covers completion, abstention, invalid references, provider failure, timeout, cancellation, and partial artifacts; repeated admission key returns same run; interrupted stages cannot claim successful completion.
- **Focused test:** `tests/research/test_runner.py`.

### M4-T02 — CLI commands

- **Depends on:** M4-T01.
- **Files:** `src/episalpha/cli.py`, CLI integration fixtures.
- **Implement exact interface:**

```bash
uv run episalpha demo seed
uv run episalpha research run --case supported --runtime fake
uv run episalpha research run --case conflicting --runtime hermes
uv run episalpha research status RUN_ID
uv run episalpha research execute RUN_ID  # Internal worker entry point
uv run episalpha research cancel RUN_ID
uv run episalpha replay RUN_ID
uv run episalpha research run --snapshot SNAPSHOT_ID --question "What changed and why might it matter?" --runtime hermes
```

- **Acceptance:** Seed command is idempotent; fake runs are visibly labeled; output includes run ID and artifact path; exit codes distinguish success from rejected/failed/incomplete outcomes; no provider key appears in output.
- **Focused test:** `tests/integration/test_cli_research.py` using Typer's test runner and temporary data directories.
- **Interface rule:** `--case` and `--snapshot` are mutually exclusive. A case includes question/cutoff. Snapshot reruns require `--question "..."`; the snapshot fixes cutoff and instrument scope, and v0.1 rejects multi-instrument snapshots for a single thesis. Admission records runtime mode, so fake and real runs cannot collide. Internal worker entry point is not a second job-admission path.

### M4-T03 — Replay and recovery semantics

- **Depends on:** M4-T02.
- **Files:** `src/episalpha/research/artifacts.py`, `src/episalpha/research/runner.py`, `src/episalpha/cli.py`.
- **Build:** Artifact replay with integrity checks, fresh-inference lineage, and explicit recovery of interrupted jobs. Add `research recover RUN_ID` that records a new attempt and does not redo already successful stages automatically.
- **Acceptance:** Saved replay invokes no provider/connector; later evidence/assessment changes do not change the replay; tampering produces `INTEGRITY_ERROR`; new inference gets new run ID; crash during a model call remains visible in attempt history.
- **Focused test:** `tests/research/test_replay.py`.

### M4-T04 — Real thesis quality review

- **Depends on:** M4-T03.
- **Files:** `docs/implementation/demo_acceptance.md`; narrow fixes to the responsible module only after recording failed criterion.
- **Build:** Run each curated case with selected model; manually inspect every material assertion, citation, numeric claim, counter-case, and missing-expectations statement.
- **Acceptance:** No invented evidence IDs; unsupported claims are corrected, rejected, or visibly unreviewed rather than labeled verified. Essential missing evidence produces abstention. Source failure stays distinguishable from no evidence. Price/consensus unknowns are explicit. Every number in the thesis traces to a cited span or a recomputed derivation (amendment A8).
- **Evidence:** Store actual run IDs, model/harness hashes, review notes, duration, usage, and costs/unknowns. No fabricated example metrics.
- **Stop:** Quality failure is feedback for current harness, not permission to weaken validators.

### Gate G4

```bash
uv run episalpha demo seed
uv run episalpha research run --case supported --runtime fake
uv run pytest -q tests/research tests/integration/test_cli_research.py
```

Also run section 4.3 checks and complete the three real-case reviews from M4-T04. The CLI is now a valid technical demonstration even before browser delivery.

---

## 11. M5 — Browser workbench and Obsidian

**Goal:** Make reasoning and its limitations inspectable with minimal frontend complexity.

### M5-T01 — Browser shell and research view

- **Depends on:** G4.
- **Files:** `apps/streamlit_app.py`, shared application service only if already present and required.
- **Build:** Four tabs: Research, Evidence, Knowledge, Experiments. Initially populate Research; show explicit placeholders for unfinished tabs. Use form submission, durable run IDs, persisted job state, and the background-worker service from M4. Do not run the 300-second research loop on the Streamlit render path.
- **Acceptance:** Page reruns, tab changes, and browser refresh do not duplicate a research job. User sees running/failed/partial/abstained status, cancel action, model/harness, elapsed time, and saved-replay/live labels.
- **Focused test:** `tests/ui/test_research_view.py` with Streamlit's testing utilities and fake services.
- **Rule:** UI calls application services; it does not implement research prompts, SQL, or temporal policy itself.

### M5-T02 — Evidence inspection and local graph

- **Depends on:** M5-T01.
- **Files:** `src/episalpha/knowledge/query.py`, `apps/streamlit_app.py`.
- **Build:** Assertion-to-claim-to-span drilldown; source passages; timestamps; semantic review status; derivation chain for numeric claims (inputs, `method`@`version`, value — amendment A8); relationship table; small selected-thesis graph with typed nodes and readable relationship labels.
- **Acceptance:** Every displayed node/edge belongs to selected snapshot/run; unsupported status is visible; source text is rendered safely; graph limits are bounded; relation table remains usable if graphical layout fails.
- **Focused test:** `tests/knowledge/test_query.py` and, if needed, a small UI test extension.
- **Graph budget:** Default maximum 50 nodes around selected thesis. No whole-universe visualization or graph-layout research.

### M5-T03 — Deterministic Obsidian exporter

- **Depends on:** M5-T02.
- **Files:** `src/episalpha/knowledge/export_obsidian.py`, `src/episalpha/cli.py`.
- **Implement:**

```bash
uv run episalpha export obsidian --run RUN_ID --output .episalpha/exports/vault
```

- **Build:** Markdown notes with flat properties, safe stable-ID filenames, quoted `[[links]]`, source locators, claim status, relation notes where needed, and export manifest. Separate `generated/<run_id>/` from user-owned `annotations/`.
- **Acceptance:** Export only selected run's records; all generated links resolve; repeated unchanged export is byte-stable; filenames cannot traverse paths; user notes are untouched; same-run modified generated files cause a conflict or new export destination rather than silent overwrite.
- **Focused test:** `tests/knowledge/test_obsidian_export.py`.
- **Scope:** No community-plugin dependency, no live bidirectional sync, no automatic import of edited notes into canonical evidence.

### M5-T04 — Browser walkthrough and usability correction

- **Depends on:** M5-T03.
- **Files:** `apps/streamlit_app.py`, `docs/implementation/demo_script.md`.
- **Build:** Six-minute walkthrough: select case; view thesis; inspect quote; inspect contradiction; browse graph/export; show saved replay. Reserve experiment segment for M6.
- **Acceptance:** Owner can navigate from thesis assertion to original passage in at most three deliberate clicks; missing information is visible without opening logs; Obsidian opens exported vault with working local links.
- **Focused test:** `tests/ui/test_workbench.py` for core navigation; record manual Obsidian check separately.

### Gate G5

```bash
uv run streamlit run apps/streamlit_app.py --server.address 127.0.0.1
uv run pytest -q tests/ui tests/knowledge
```

Also run section 4.3 checks. Record manual browser and Obsidian acceptance. Browser remains localhost-only for v0.1.

---

## 12. M6 — AVO-inspired research-quality experiment

**Goal:** Demonstrate controlled procedural improvement against fixed evidence-based tasks, including the possibility that a challenger is rejected.

### 12.1 Experimental contract

Prepare 24 small human-reviewed cases as an engineering dataset:

- 12 development cases with labels available for failure analysis.
- 6 validation cases, labels accessible only to evaluator.
- 6 final check cases, inputs/labels inaccessible to candidate author and withheld until configuration is frozen.

Group by source/document/event family before splitting; do not put near-duplicate evidence in different partitions. This sample is for testing experimental machinery and preliminary quality, not statistical proof of generalization.

Required case types include extraction, source attribution, numerical units/periods, contradiction, duplicate lineage, missing evidence, future evidence, and injected instructions in source text.

For open-ended material, record human judgments with rubric and reviewer identity. Deterministic quote matching alone cannot establish semantic support. An optional LLM judge is secondary and cannot rewrite gold labels.

### 12.2 Candidate surface

Initial baseline configuration includes:

```json
{
  "schema_version": "1",
  "contradiction_search": false
}
```

For the first campaign, permit **one configuration mutation only**:

```json
{
  "parent_harness_id": "<existing baseline id>",
  "hypothesis": "An explicit contradiction retrieval step improves recall without adding unsupported claims.",
  "patch": [
    {"op": "replace", "path": "/contradiction_search", "value": true}
  ]
}
```

The mandatory critic and counter-case remain present in both variants. The flag enables one additional bounded retrieval step over the same frozen corpus; it does not remove existing evidence requirements or expand data access.

Allow no mutation of evaluator, labels, dataset partitions, budgets, timestamps, schemas, permissions, or canonical evidence. No arbitrary candidate Python code. Candidate author may be the same model in a separate context, receiving development failures and the allowlisted patch schema only.

Default campaign budget: one proposed challenger. Keep baseline if challenger fails. Do not search until a favorable result appears.

### 12.3 Metric definitions and predeclared decision rule

Use case-level numerators/denominators and pooled totals over the same eligible cases. Keep required-fact and contradiction IDs in human-owned labels so repeated wording does not inflate counts.

| Metric | Definition |
|---|---|
| Citation correctness | Emitted citation links matching the labeled supporting passage / emitted citation links; source existence alone is insufficient |
| Supported-claim precision | Factual claims assessed supported / emitted factual claims; hypotheses are reported separately, not counted as supported facts |
| Required-fact recall | Distinct expected fact IDs correctly recovered / expected fact IDs |
| Contradiction recall | Distinct expected contradiction IDs correctly recovered / expected contradiction IDs |
| Correct abstention | Cases whose explicit abstain/non-abstain disposition matches label / all cases requiring that decision |
| Completion | Successfully completed required outputs / all attempted cases |

No emitted claims/citations on a case requiring them is a failure of completeness, not perfect precision. If a metric truly has no applicable labeled denominator, report `N/A`, not zero or one; another metric cannot silently replace it. Label mappings and semantic assessment provenance are recorded alongside scores.

Default validation rule, frozen before evaluating challenger:

1. Zero temporal/reference/boundary violations in both eligible baseline and challenger; an invalid baseline blocks a meaningful comparison.
2. No new unsupported material factual claims, and no reduction in pooled supported-claim precision, required-fact recall, correct abstention, or completion on applicable cases.
3. Recover at least one additional distinct labeled contradiction across validation cases, without losing a contradiction recovered by baseline.
4. Mean model-request count and median latency each remain at or below 1.5 times baseline, and every run stays within its hard budget. Report costs independently when known.
5. Run the frozen configuration on final-check cases only after passing validation. Require validity and no quality regression there; do not require a second positive improvement from this tiny sample.

If any condition fails, retain baseline. These thresholds are engineering choices and have no statistical-significance claim. Owner may change them only before a new campaign starts, with a new manifest/version. Case labels and evaluator code remain fixed during a campaign.

### M6-T01 — Labeled cases and deterministic metrics

- **Depends on:** G5.
- **Files:** `src/episalpha/evaluation/cases.py`, `src/episalpha/evaluation/scoring.py`, `eval_cases/manifests/` and development fixtures.
- **Build:** Versioned case schema, partition checks, label loading from evaluator-only location, evaluator hash, and per-case metrics.
- **Metrics:** Citation correctness; numeric-correctness rate (share of model-proposed numbers matching recomputation before repair, amendment A8); supported-claim precision; required-fact recall; contradiction recall; correct abstention; temporal violations; completion; model requests; available usage/cost; latency.
- **Acceptance:** Correct metric direction and denominators; empty answers cannot win by avoiding claims; failed cases remain in denominator; cross-partition duplicate families fail; labels cannot be loaded by research tool paths.
- **Focused test:** `tests/evaluation/test_scoring.py`.
- **Owner checkpoint:** Human validates labels before they become frozen evaluator inputs.

### M6-T02 — Candidate validation and lineage

- **Depends on:** M6-T01.
- **Files:** `src/episalpha/evolution/candidates.py`, candidate fixtures.
- **Build:** Strict one-operation patch validator; parent/candidate hashes; hypothesis/rationale; campaign/trial records; separate candidate directory; no in-place modification of baseline.
- **Acceptance:** Only allowed flag change passes; empty, duplicate, multiple, arbitrary-file, or budget-changing patches fail; failed/abandoned proposals are retained in ledger; active harness remains unchanged.
- **Focused test:** `tests/evolution/test_candidates.py`.

### M6-T03 — Offline campaign runner

- **Depends on:** M6-T02.
- **Files:** `src/episalpha/evolution/campaign.py`, `src/episalpha/cli.py`, `src/episalpha/research/runner.py` for the bounded optional retrieval step.
- **Implement:**

```bash
uv run episalpha experiment compare --campaign demo-v1 --runtime fake
uv run episalpha experiment compare --campaign demo-v1 --runtime hermes
```

- **Build:** Development failure summary; candidate proposal; schema validation; paired baseline/challenger runs on identical snapshots and fixed budgets; validation comparison; frozen-config final check; outcome ledger.
- **Acceptance:** Candidate author sees no hidden inputs/labels; research worker sees only its current case input; evaluator alone loads labels; experiment/cache identities include runtime mode, provider/model, snapshot, harness/config, evaluator/label hashes, and attempt. Fake and real campaigns sharing display name `demo-v1` get distinct execution IDs; fake results can never satisfy live results. Interrupted/failed trials remain recorded; no automatic baseline replacement.
- **Focused test:** `tests/evolution/test_campaign.py` using fake runtime; one explicit live campaign required for final demo.
- **Control:** Report two independent fresh runs per variant/case for the small demonstration if budget allows; otherwise report single-run variability limitation. Seeds, when supported, are recorded, not treated as determinism guarantees.

### M6-T04 — Experiment report and browser comparison

- **Depends on:** M6-T03.
- **Files:** `src/episalpha/evaluation/reporting.py`, `apps/streamlit_app.py`, `docs/implementation/demo_script.md`.
- **Build:** Candidate diff, per-case paired results, aggregate numerator/denominator, failures, usage/cost, latency, and accept/reject decision with reasons.
- **Decision order:** Apply section 12.3 defaults declared in the campaign manifest before viewing validation results. Report each gate separately; no hidden weighted score.
- **Acceptance:** Report cannot hide failed trials or imply financial alpha; actual measured outcomes replace illustrative numbers; candidate rejection is a complete valid result; final-check cases are not reused for tuning after exposure.
- **Focused test:** `tests/evaluation/test_reporting.py`.
- **Owner action:** Any promotion is explicit, versioned, and linked to report; choosing not to promote is acceptable.

### Gate G6

```bash
uv run pytest -q tests/evaluation tests/evolution
uv run episalpha experiment compare --campaign demo-v1 --runtime fake
```

Also run section 4.3 checks and complete one real-provider campaign. Store manifest, labels/evaluator hashes, all trial IDs, actual comparison report, and owner decision. Do not invent an improvement to satisfy this milestone.

---

## 13. M7 — Demo acceptance, recovery, and handoff

**Goal:** Deliver a repeatable demonstration with honest failure behavior and a clear implementation handoff.

### M7-T01 — Cross-boundary acceptance suite

- **Depends on:** G6.
- **Files:** `tests/integration/test_demo_acceptance.py`, focused fixtures; responsible production module only if a failure needs correction.
- **Build:** End-to-end tests covering the acceptance matrix below; use fake provider/runtime where external model behavior is not what is being verified.
- **Acceptance:** All deterministic invariants pass; no fixture is mislabeled live; snapshot/reference boundaries remain intact across UI, tools, storage, replay, export, and evaluation.
- **Stop:** Fix causes without relaxing frozen expectations.

### M7-T02 — Demo packaging and smoke command

- **Depends on:** M7-T01.
- **Files:** `scripts/demo_smoke.py`, `README.md`, `docs/implementation/demo_acceptance.md`.
- **Build:** Offline smoke script creates temporary state, seeds fixtures, runs three cases, replays output, exports vault, and produces comparison artifact. Preserve user state and print output locations.
- **Acceptance:** Fresh environment follows README successfully; script exits nonzero on any failed assertion; recorded replay works without provider/network; DB/object/run backup can be restored together and hashes checked.
- **Focused test:** `tests/integration/test_smoke_script.py`.

### M7-T03 — Final owner walkthrough

- **Depends on:** M7-T02.
- **Files:** `docs/implementation/demo_script.md`, `docs/implementation/demo_acceptance.md`, `docs/implementation/progress.md`.
- **Perform:** Real-provider research run; saved replay; source inspection; contradiction/unknowns; local graph; Obsidian export; measured candidate comparison; intentional source/model failure.
- **Acceptance:** Record actual machine, versions, run IDs, latency/usage, limitations, and all G0–G7 outcomes. No required acceptance item remains silently incomplete.
- **Handoff:** Document next eligible work: forward forecast logging, then optional paper/evaluation lab. Do not start those features during final walkthrough.

### Gate G7

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src/episalpha
uv run pytest -q -m "not live"
uv run python scripts/demo_smoke.py
uv run pytest -q -m live tests/integration/test_hermes_runtime.py tests/integration/test_runtime_boundary.py
```

Final live checks require configured credentials/runtime. Record BLOCKED if unavailable; offline success is reported separately.

---

## 14. End-to-end acceptance matrix

| ID | Scenario | Required observable result | Primary owner |
|---|---|---|---|
| A01 | Valid supported case | Completed thesis; material assertions resolve to spans/hypotheses | M4 |
| A02 | Conflicting sources | Opposing evidence and assessment visible; no silent deletion | M4/M5 |
| A03 | Essential evidence missing | Explicit abstention and useful next inquiry | M4 |
| A04 | Source unavailable | `SOURCE_FAILED`; never fabricated no-data answer | M2/M4 |
| A05 | Future source added later | Existing snapshot and saved run unchanged | M2/M4 |
| A06 | Restatement/correction | Historical query selects correct qualifying version | M1/M2 |
| A07 | Fabricated citation or quote | Candidate rejected or bounded repair succeeds visibly | M1/M4 |
| A08 | Injection in document | Stored as untrusted source text; no unauthorized tool/action | M3/M7 |
| A09 | Worker attempts forbidden access | Cannot read evaluator/canonical DB or modify evidence/harness | M3 |
| A10 | Budget/timeout/cancel | Worker stops; incomplete state and spent usage retained | M3/M4 |
| A11 | Browser refresh | Existing job remains; no duplicate model spend | M5 |
| A12 | Saved replay with network blocked | Same recorded artifacts; zero provider requests | M4 |
| A13 | Fresh run on same snapshot | New run ID; prior run untouched; variability visible | M4 |
| A14 | Invalid graph relation | Type/reference validation failure | M1/M5 |
| A15 | Obsidian export repeated | Stable generated output; annotations preserved; links resolve | M5 |
| A16 | Candidate edits forbidden field | Patch rejected and attempt recorded | M6 |
| A17 | Empty/failed candidate answer | Completeness/recall penalty; cannot win by omission | M6 |
| A18 | Candidate does not improve | Report honestly rejects it; milestone can still pass | M6 |
| A19 | Crash and recovery | Stage/attempt history preserved; no invented completion | M4/M7 |
| A20 | Source/object artifact altered | Integrity check fails; no silent regeneration | M2/M4 |
| A21 | Copied articles cite same source | Common lineage visible; no invented independent confirmations | M2/M5 |
| A22 | Unknown usage/pricing | Unknown displayed; no fabricated EUR total or cap claim | M3/M5 |
| A23 | Historical reconstruction | Model-hindsight limitation and actual execution time visible | M1/M5 |
| A24 | Evaluator input changed | Hash/version mismatch blocks comparison until re-declared | M6 |

**Semantic quality target:** No material assertion may be presented as human-verified without recorded human assessment. Structurally valid unreviewed claims remain visibly unreviewed.

**Performance target:** Saved three-case fixture corpus opens locally within 5 seconds after application warm-up on the recorded demo machine. Live research completes within configured 300-second budget or exits explicitly. Measure these; do not promise them before tests.

**Cancellation target:** Parent worker and children stop within 10 seconds of cancellation or watchdog expiry in the integration environment. Report any transport billing ambiguity separately from local process termination.

---

## 15. Definition of done

### 15.1 Working demo

- [ ] All required gates G0–G7 have actual recorded results.
- [ ] Three curated research cases and labeled synthetic adversarial cases exist.
- [ ] Browser supports research, evidence, knowledge, and experiment inspection.
- [ ] CLI can seed, run, inspect, cancel, recover, replay, export, and compare.
- [ ] At least one actual Hermes/provider integration is verified at the pinned version.
- [ ] Source payloads, normalized text, spans, and manifests are traceable.
- [ ] Every material thesis assertion has typed claim/hypothesis references.
- [ ] Unknowns, semantic review status, and contradictions are visible.
- [ ] Historical source/graph retrieval obeys frozen snapshot boundaries.
- [ ] Saved replay is network-free and distinct from fresh inference.
- [ ] Agent cannot modify canonical data, evaluator, labels, or active harness.
- [ ] Obsidian export has valid links and preserves user annotations.
- [ ] One actual bounded challenger experiment has an honest report.
- [ ] Default automated suite runs offline without model credentials.
- [ ] README and demo script work from a clean checkout.

### 15.2 Evidence of quality

Store actual outputs and checks, not claims such as “works perfectly.” A valid handoff includes:

- Installation/lock information.
- Runtime/model/harness versions.
- Task and milestone completion records.
- Offline and live test outcomes separately.
- Reviewed research run IDs and remaining semantic limitations.
- Actual experiment report, including unsuccessful candidate results.
- Measured latency, request usage, and cost where available.
- Known operational limitations and next bounded task.

### 15.3 Follow-on milestones after v0.1

Only after demo gates pass:

1. **Forward observation:** Timestamp forecasts before outcomes; define forecast target and benchmark explicitly.
2. **Outcome evaluation:** Settle one horizon with exchange calendars, corporate actions, and defensible price/cost assumptions. Candidate quantitative methods deferred by A8: event-window reaction vs a benchmark (needs adjusted prices), factor baselines (Fama-French), Deflated Sharpe and PBO — see blueprint §12.
3. **Paper portfolio:** Add ledger and deterministic proposal/risk boundary as a separate scoped feature.
4. **Graph-value evaluation:** Compare typed-graph retrieval against simpler retrieval on fixed tasks.
5. **Infrastructure migration:** Add PostgreSQL or a graph engine only when concurrency/query requirements justify it.
6. **Broader evolution:** Expand candidate surface only after evaluator validity and isolation are demonstrated.

No positive alpha result is required to finish an engineering milestone. Financial conclusions require a separate, adequately designed research protocol.

---

## 16. Research references and implementation cautions

External documentation was reviewed on 20 September 2026. Resolve and pin actual compatible versions during M0; this plan does not invent a Hermes commit or assert future model capabilities.

1. [Hermes official repository](https://github.com/NousResearch/hermes-agent) — use this upstream rather than a similarly named mirror.
2. [Hermes programmatic integration](https://hermes-agent.nousresearch.com/docs/developer-guide/programmatic-integration) — supported integration surfaces; verify against pinned version.
3. [Hermes tools/runtime](https://hermes-agent.nousresearch.com/docs/developer-guide/tools-runtime) and [MCP integration](https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp) — tool discovery, filtering, and external-tool integration.
4. [Hermes skills](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills) — learning behavior must be explicitly controlled in frozen research runs.
5. [Obsidian Graph view](https://help.obsidian.md/plugins/graph), [Properties](https://help.obsidian.md/properties), [Bases](https://help.obsidian.md/bases) — notes/links and structured Markdown; these do not replace domain validation.
6. [W3C PROV-O](https://www.w3.org/TR/prov-o/) — provenance concepts to borrow without requiring an RDF deployment.
7. [FIBO](https://spec.edmcouncil.org/fibo/) — reference terminology; selective reuse rather than wholesale ontology adoption.
8. [AVO paper](https://arxiv.org/abs/2603.24517) and [NVIDIA architecture discussion](https://developer.nvidia.com/blog/nvidia-avo-reaches-100-on-arc-agi-3-demonstrating-a-frontier-level-general-purpose-architecture-for-long-horizon-autonomous-agents/) — architectural inspiration, not evidence of financial alpha.
9. [DatedGPT](https://arxiv.org/abs/2603.11838) — model-training hindsight is separate from retrieval timestamp filtering.
10. [SEC EDGAR access](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data) — availability, corrections, identifiers, and fair access.
11. [Streamlit forms](https://docs.streamlit.io/develop/concepts/architecture/forms) — deliberate submission and rerun behavior.
12. [Ollama API compatibility](https://docs.ollama.com/api/openai-compatibility) — subset compatibility requires capability tests.
13. [TradingAgents changelog](https://github.com/TauricResearch/TradingAgents/blob/main/CHANGELOG.md) — useful connector/PIT reference; not a required dependency for v0.1.
14. [TradingAgents dataflows](https://github.com/TauricResearch/TradingAgents/tree/main/tradingagents/dataflows) — the source set EpisAlpha's families follow. **Their published `assets/schema.png` is older than their code**: the diagram shows Bloomberg, Reuters, EODHD and X, while the modules are Alpha Vantage, FRED, Yahoo Finance, SEC EDGAR, Reddit, StockTwits and Polymarket, plus `date_window.py` for point-in-time caching.
15. [Alpha Vantage documentation](https://www.alphavantage.co/documentation/) — `TIME_SERIES_DAILY` is free; `TIME_SERIES_DAILY_ADJUSTED` is premium. Free tier nominally 25 requests/day and 5/minute, in practice ~1 request/second.

---

## 17. Start here

~~Execute **M0-T01 only** in the first coding session.~~ **M0 and M1 are complete and gated** (G0 offline passed with the live portion partial; G1 passed; schema version frozen at `1`). M2 is complete and gated (G2, owner checkpoint outstanding). **Execution now runs from [`implementation/README.md`](implementation/README.md)** (amendment A10): pick the next task in `implementation/STATUS.md` — currently **M0-T04**, then M0-T05, M0-T06, M1-T05, M2-T05, M2-T06, M3-T01. Current state, real command output and open blockers live in `docs/implementation/progress.md`.

Do not ask a coding model to “implement this entire plan.” Give it the current task, relevant contracts, and acceptance tests. Keep architectural decisions stable, checkpoints explicit, and subsequent work gated by observable results.
