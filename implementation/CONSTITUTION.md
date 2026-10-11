# Global constitution

Binding on every phase and every task. A phase constitution may add articles; it may never relax
one here. If a task seems to require breaking an article, stop and report `BLOCKED`. The owner
decides; the coding model does not.

Sources: `CLAUDE.md`, and plan §§1–4 (`EpisAlpha_MVP_Milestone_Implementation_Plan.md`).

## I. Epistemic integrity

1. **Agents propose; deterministic systems dispose.**
   - Model output is a *candidate*.
   - Only the host validates, assigns canonical IDs, and passes records to later stages through
     `RuntimeContext`.
   - A model can never overwrite an existing canonical ID.
2. **Every user-visible material statement is a `ThesisAssertion`** with claim and/or hypothesis
   references. Never add a free-text summary field that bypasses them.
3. **Valid schema plus a clean citation does not make a claim `supported`.** Only a recorded
   `SemanticAssessment` does. Assessments are versioned, never overwritten.
4. **Numbers are reported or recomputed, never asserted (A8).** Every number traces to a cited
   span or to a registered derivation the validator recomputes. The model never supplies a
   computed value.
5. **An `unverified` source cannot be the sole support for an assertion (A2).**
6. **Frozen vocabulary (plan §3.3).** Extending it is a schema change that needs owner approval.
   Schema version is `1`.

## II. Time

7. **Six clocks, never collapsed:**
   - economic event time;
   - publication time;
   - when that exact version became publicly available;
   - capture time (`ingested_at`);
   - research cutoff;
   - run execution time.
8. **Eligibility.**
   - A publication date alone never proves a fetched version existed then.
   - Unverified availability falls back to `first_capture`.
   - Old versions are retained; the latest *qualifying* version wins.
9. **Creation time is not backdated.** A claim created today keeps today's `created_at`.
10. **Historical runs display:** "Retrospective research; model training knowledge may include
    later events."

## III. Honest outcomes

11. **Failure states stay distinct:**
    - `ABSTAINED` means essential evidence is missing.
    - `REJECTED` means invalid references could not be repaired.
    - `PARTIAL` is not `FAILED` or `TIMED_OUT`.
    - A provider outage is never turned into an abstention.
12. **`SOURCE_FAILED` is not `NO_DATA`.** Partial work is preserved when a run fails.
13. **Unknown stays unknown.** Usage, pricing and cost are never estimated into a number.
    `cost_eur` stays `None` in v0.1.

## IV. Verification integrity

14. **Never weaken a test to make it pass.** Never weaken an assertion, skip a failing test,
    regenerate an expected answer, or relax a validator to get a pass.
15. **`FakeRuntime` output is always labeled as a fixture.** It is never evidence that a live
    integration passed. A blocked live gate stays blocked.
16. **Do not invent upstream facts.** That covers Hermes API arguments, commit IDs, model
    capabilities, provider behaviour and evaluation results. Pin and record what was actually
    observed.
17. **Human-owned evidence annotations and evaluation labels are not repair targets.**
18. **The default suite runs offline.** It needs no credentials and no network. Anything else
    carries the `live` marker.

## V. Engineering

19. **Scope.**
    - One task per session.
    - 1–3 implementation files plus one focused test file.
    - Split a task rather than exceed this.
    - Never build later-milestone features early.
20. **Data conventions.**
    - IDs are application-generated and filesystem-safe; user titles and model text are never
      paths.
    - Timestamps are timezone-aware UTC with an explicit offset.
    - Money and measurements are decimal strings plus units, never floats.
21. **Limits live in one place.** All limits and budgets live in `Settings.limits`
    (`src/episalpha/settings.py`). No scattered constants.
22. **Storage.** stdlib `sqlite3` with WAL, foreign keys, busy timeout and short transactions;
    no ORM. One active research job.
23. **Exporters are never canonical. Connectors never infer conclusions. The evaluator never
    executes candidate code. Labels live outside every agent-accessible path.**
24. **Minimal dependencies.**
    - Runtime: Pydantic, Typer, HTTPX, Streamlit. Dev: pytest, Ruff, mypy.
    - Add a dependency only when a task requires it.
    - Untyped Hermes imports stay inside `runtime/hermes.py`.
    - Strict mypy is never relaxed globally.
25. **No model names in code.** The research model and the coding model are independent choices.
    The research route lives only in config (`config/*.toml`, `ENV:` references).

## VI. Secrets

26. **Credentials appear only as `ENV:<name>` references.**
    - Values live in the git-ignored `.env`.
    - Never print, log, commit or paste a secret value, including in journals, `PROGRESS.md`,
      test fixtures and error messages.

## VII. Observability: the Diagnose layer (A11, A14)

27. **Observable by default, whole system.**
    - Every I/O or trust boundary emits one **OpenTelemetry span** through
      `episalpha.observability` (from M0-T06). That covers AI and non-AI boundaries alike.
    - A research run is **one trace**: root span `research.run`, `session.id` = `run_id`.
    - CLI commands, UI actions, ingestion, export, replay and recovery, M6 campaigns and M8 skill
      evaluations each get their own traces. Evaluation trials link to their run traces.
    - Event names used in the task packs map to spans as follows:

      | Pack event name | Span name | OpenInference kind |
      |---|---|---|
      | `connector.request/response/refused` | `connector.fetch` (outcome as attribute) | `CHAIN` |
      | `snapshot.built` | `snapshot.freeze` | `CHAIN` |
      | `stage.transition` | `stage.<name>` (span start and end) | `AGENT` |
      | `model.call` | `model.call` | `LLM` |
      | `tool.call` | `tool.<name>` (`search_evidence` is `RETRIEVER`) | `TOOL` |
      | `validation.completed` | `validation`, with one span event per check | `EVALUATOR` |
      | `repair.attempt` | `repair.attempt` | `CHAIN` |
      | `run.terminal` | the end of `research.run` (status and reason as attributes) | `CHAIN` |
      | `export.completed` | `export.obsidian` | `CHAIN` |
      | `eval.trial` / `eval.decision` | `eval.trial` / `eval.decision` | `EVALUATOR` |
      | `skill.*` | `skill.<action>` | `CHAIN` (`skill.evaluated` is `EVALUATOR`) |

28. **Diagnostics are never canonical.**
    - Canonical state lives in SQLite and the content-addressed object store.
    - No application logic reads logs or Phoenix to decide anything.
    - A Phoenix outage or export failure never fails a run. Spans still go to the JSONL
      fallback.
29. **Content policy (owner decision, 2026-10-10).**
    - The **local Phoenix exporter** receives full content: prompts, completions, tool inputs
      and outputs, validation details.
    - The **JSONL fallback** (`<data_root>/logs/spans.jsonl`) receives metadata only: names,
      timings, IDs, hashes, sizes, counts, status.
    - A `RedactionSpanProcessor` strips every resolved credential value **before any exporter**.
    - Phoenix binds to `127.0.0.1` only. It is unreachable from the worker container, keeps
      data for a bounded retention period, and is never exported to third parties.
30. **Every task leaves evidence.** Each task ends with three things:
    - a `diagnose.py` run showing no regression;
    - a journal entry;
    - a `PROGRESS.md` row with real command output.

    From M0-T06 on, the task's expected spans must also be visible.

    A delivery that cannot be explained from this evidence is not done.

## VIII. Learning (A13): learn offline, act frozen

31. **Runs never change the skills they use.**
    - During a run, the research model works with a frozen, read-only, versioned skill set.
    - The skill-set hash is part of the harness hash, so every run stays reproducible.
32. **The only path to a new skill is gated.** The steps, in order:
    1. propose (`propose_skill`, recorded as data);
    2. deterministic screening;
    3. offline paired evaluation (no regression, plus a targeted gain);
    4. **human approval**, showing diff, provenance and evaluation report;
    5. read-only use in later runs.

    Nothing is auto-promoted.
33. **Every skill is provenance-linked and revocable.**
    - Each skill records the runs, trajectories and evidence spans it came from.
    - Revoking a source revokes every skill derived from it.
    - Self-generated skills can carry poisoned instructions that slip past an LLM judge
      (SkillJack, 2026).
34. **Skills are procedural, never factual.**
    - No tickers, dated facts, numbers with units or URLs.
    - Historical runs use only skills promoted at or before their research cutoff (§II; plan §3.5
      rule 9).
35. **Hermes' native learning stays off.** That means memory, user profile, session search,
    background review, curator and Skills Hub. These write state with no provenance and spend
    requests no one budgeted.

