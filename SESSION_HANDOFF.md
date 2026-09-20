# EpisAlpha — Session Handoff for Continuation

**Date:** 20 September 2026
**From:** opencode session (planning + M0-T01 implementation)
**To:** Claude Code (Opus 5) or any capable coding agent
**Purpose:** Continue implementation from the current verified state, without losing any decision, contract, or working rule established so far.

---

## 1. Read these files first, in this order

| Priority | File | Why |
|---|---|---|
| 1 | `CLAUDE.md` | Already-written repo instructions. Claude Code loads it automatically; other agents: read it manually. |
| 2 | `EpisAlpha_MVP_Milestone_Implementation_Plan.md` | Governing plan. Frozen contracts, controlled vocabulary, temporal rules, task cards M0-T01 … M7-T03, gates G0–G7, acceptance matrix A01–A24. **This file wins over the blueprint wherever they disagree.** |
| 3 | `EpisAlpha_Architecture_and_Implementation_Blueprint.md` | Long-term direction. **Do not load fully**; consult specific sections only when a task card points there. |
| 4 | `README.md` | Current scope statement. |
| 5 | This file | Session state + continuation rules. |

Working rule: read only the current task card, its gate, relevant contract sections (plan §§1–4), and directly related code/tests. Never ask an agent to "implement the whole plan."

---

## 2. What this session accomplished

1. **Architecture review** of the blueprint (all 30 sections), cross-checked against primary sources: official Hermes docs (NousResearch/hermes-agent), TradingAgents v0.5.0 changelog (2026-09-18), NVIDIA AVO paper (arXiv:2603.24517) + Aug 2026 architecture blog, DatedGPT (arXiv:2603.11838) on model-weight lookahead bias, SEC EDGAR access rules, Obsidian docs (Graph/Properties/Bases), W3C PROV-O, FIBO, Ollama OpenAI-compatibility subset, Streamlit forms.
2. **Key review verdicts** (already incorporated into the plan — do not re-litigate):
   - Browser-first (Streamlit) for demo; thin CLI underneath sharing application services.
   - Obsidian = derived one-way export only, never canonical storage; SQLite is the system of record.
   - Small ontology: 8 object types + 7 relation predicates (frozen in plan §3.3–3.4). No Neo4j in v0.1.
   - Point-in-time retrieval does NOT stop model-weight hindsight → historical runs must display the retrospective-research label; forward forecast accumulation starts early but is not v0.1 scope.
   - Claim/evidence-span model moved from blueprint's Phase 4 into the first vertical slice.
   - Evolution (AVO-inspired) = one bounded offline config mutation on research quality, never financial-return optimization in v0.1.
   - Hermes upstream corrected to **NousResearch/hermes-agent**; must be probed live before architecture is built around it (M0-T03).
3. **Wrote the governing plan** `EpisAlpha_MVP_Milestone_Implementation_Plan.md` (v1.0, ~1124 lines, validated: 30 ordered task cards, 8 gates, backward-pointing dependencies only, 24 acceptance scenarios A01–A24, JSON examples parse, shell commands parse, tables consistent).
4. **Implemented and verified M0-T01** (details in §3 below).

---

## 3. Current verified state (M0-T01 = DONE)

Files created this session:

```
pyproject.toml            # hatchling build; typer dep; dev group (mypy/pytest/ruff)
                          # pytest: live marker registered, testpaths=tests
                          # ruff: line-length 100, py312, E/F/I/B/UP, extend-exclude=["*.md"]
                          # mypy: strict, files=src/episalpha, warn_unreachable
src/episalpha/__init__.py # __version__ = "0.1.0"
src/episalpha/cli.py      # Typer app; invoke_without_command=True; --version option
tests/integration/test_package.py  # 2 tests: version matches metadata; CLI prints version
.gitignore                # .episalpha/, .env*, caches, *.Zone.Identifier
README.md                 # M0-T01 scope only; dev commands
uv.lock                   # locked (19 packages)
CLAUDE.md                 # repo instructions for coding agents
```

Verification actually run and passing (2026-09-20):

```
uv sync --all-groups                                  # OK — editable install
uv run episalpha --version                            # prints 0.1.0
uv run ruff check .                                   # All checks passed
uv run ruff format --check .                          # 3 files already formatted
uv run mypy src/episalpha                             # Success: no issues in 2 source files
uv run pytest -q -m "not live"                        # 2 passed
git diff --check                                       # clean
```

Two defects were found and fixed during M0-T01 (record so they are not re-introduced):

1. Typer callback with `no_args_is_help=True` rejected bare `--version` → fixed with `invoke_without_command=True` on the `typer.Typer(...)` constructor.
2. `ruff format --check` was reformatting Python blocks inside the blueprint Markdown → fixed with `extend-exclude = ["*.md"]` under `[tool.ruff]`. **Never remove this exclusion; the blueprint is a frozen owner document.**

Git state: one commit exists (`8b7b4c6 "the first plan"` — owner's commit of the two planning .md files). Everything else is **untracked**. Commits are an explicit owner action — do not commit unless asked.

Environment: uv 0.11.7, CPython 3.12.3 (/usr/bin/python3), Linux/WSL.

---

## 4. How to continue — exact next steps

### Step 1: create the handoff record

M0-T02 requires `docs/implementation/progress.md`. The directory `docs/implementation/` already exists (created, empty). First continuation action:

1. Create `docs/implementation/progress.md` with the table format from plan §2.4.
2. Record M0-T01 as DONE with the verification lines from §3 above (exact command + actual result).

(If continuing in Claude Code: `CLAUDE.md` already mandates this format and cadence.)

### Step 2: implement M0-T02

Task card: plan §6, `M0-T02 — Resolve settings and record execution state`.

- Files: `src/episalpha/settings.py`, `config/demo.example.toml`, `docs/implementation/progress.md`, `README.md` (update).
- Build: validated settings object (Pydantic v2 — **add `pydantic>=2` to dependencies now**, it is planned for M0-T02 usage), local paths, selected companies/theme placeholders, source IDs, provider route, and the §3.8 limit table (max wall time 300 s, 8 model requests, 12 tool calls, 4 000 output tokens, 128 KiB request body, 32 KiB tool result, 6 search hits, 1 repair, 1 retry; one active job).
- Constraints:
  - Credentials are **environment references** only (e.g. `ENV:EPISALPHA_PROVIDER_KEY`), never literal values in tracked config.
  - Unknown fields / invalid limits must fail with actionable messages (extra="forbid", strict numeric bounds).
  - Relative paths resolve from an explicit project/data root; loading config performs **no network calls**.
  - Keep every numeric limit in this one validated settings object — no scattered constants.
- Acceptance: `tests/contracts/test_settings.py` covering invalid-limit rejection, unknown-field rejection, path resolution, offline load. Run the four standard checks (ruff check / ruff format --check / mypy / pytest -m "not live").
- Owner inputs still unresolved (record as BLOCKED in progress.md, keep building offline):
  - which research model/provider + credential mechanism is available;
  - the three demo companies + theme;
  - price source choice;
  - optional EUR cap.

### Step 3: implement M0-T03 (live probe — may be BLOCKED)

Task card: plan §6, `M0-T03 — Probe official Hermes and one model route`.

- Files: `scripts/probe_hermes.py`, `config/runtime.lock.json`, `docs/implementation/hermes_probe.md`, `tests/integration/test_hermes_probe.py` (marked `live`).
- Pin the exact upstream: `NousResearch/hermes-agent` (NOT `hermes-agent-org/hermes`). Record inspected commit hash, install approach, Python compatibility, entry point used (subprocess CLI vs `run_agent.AIAgent` import vs TUI-gateway JSON-RPC vs API server — choose what the probe actually verifies), and real config keys.
- Probe must verify: one typed read-only synthetic tool, fresh profile, tool allowlist, structured final output, tool trace, usage reporting, cancellation, main/auxiliary model routing.
- **Rules:** do not invent Hermes API arguments — only record what the probe actually observed. If credentials/model are unavailable, mark the gate G0 live portion BLOCKED and continue only with offline scaffolding tasks that do not depend on it. Never fake a live pass.
- Gate G0 = §6 of the plan: settings tests + package tests + `pytest -q -m live tests/integration/test_hermes_probe.py` + the four standard checks.

### Step 4 and beyond

M1 (contracts: knowledge → research → temporal → validator) → M2 (storage/objects/connectors/snapshots) → M3 (runtime: port+fake+tools → relay → hermes adapter → sandbox) → M4 (runner+CLI+replay+quality review) → M5 (Streamlit tabs, graph query, Obsidian export) → M6 (evaluation cases, candidate patch, campaign, report) → M7 (acceptance suite, smoke script, walkthrough). Task cards contain files, acceptance criteria, focused test paths, and stop conditions for each. Dependency graph is linear; do not skip gates.

---

## 5. Non-negotiable working rules (condensed from plan §2 + CLAUDE.md)

1. **One task card per session.** Target 1–3 implementation files + 1 focused test file. Split rather than exceed.
2. **Never** weaken an assertion, skip a failing test, regenerate expected output, or relabel `FakeRuntime` output as live.
3. **Never** invent Hermes API args, commit IDs, model capabilities, or evaluation results — pin and record what was actually inspected.
4. Frozen contracts: plan §3.2 objects, §3.3 vocabulary, §3.4 predicates, §3.5 temporal rules, §3.8 limits. Extending the vocabulary is a schema change requiring owner approval. Schema version is frozen at `1` after G1.
5. Six clocks, never collapsed (§3.5). `ThesisAssertion` is the only path for user-visible material statements. No free-text summary field.
6. Honest terminal states: `ABSTAINED` ≠ `REJECTED` ≠ `PARTIAL` ≠ `FAILED`/`TIMED_OUT`; provider outage never becomes a valid abstention.
7. Money/financial values = decimal strings + units; IDs application-generated and filesystem-safe; timestamps tz-aware UTC with explicit offsets.
8. Isolate untyped Hermes imports inside `runtime/hermes.py`; never globally relax mypy.
9. Four checks at every milestone gate: `uv run ruff check . && uv run ruff format --check . && uv run mypy src/episalpha && uv run pytest -q -m "not live"`.
10. Escalate to the owner after **two failed bounded attempts** on the same issue, on contract/temporal-rule changes, on missing live credentials, or when Hermes cannot meet isolation/trace requirements.
11. Record every task in `docs/implementation/progress.md`: Task / Status / Changes / Verification (exact command + actual result) / Blocker / Next.
12. Do not commit or push unless the owner explicitly asks.

Reusable per-task prompt template: plan §2.3 (copy verbatim, substitute TASK_ID).

---

## 6. Environment quirks discovered this session

- Shell has **no `apply_patch`**; large heredoc-based `git apply` works but is brittle with hunk headers. Prefer writing files directly (cat > file, or the native file-editing tools of the agent in use).
- `git apply` on untracked files requires `--no-index` or fails; simplest reliable method for new files is direct creation.
- `*.Zone.Identifier` is a Windows NTFS alternate-data-stream artifact from copying files from Windows; it is git-ignored via `*.Zone.Identifier` pattern — do not track it.
- The blueprint file `EpisAlpha_Architecture_and_Implementation_Blueprint.md:Zone.Identifier` sits next to the real blueprint; the real file is the one **without** the suffix.

---

## 7. Suggested first message to the continuing agent

```text
Continue EpisAlpha implementation from the verified state.

Read first:
1. CLAUDE.md
2. EpisAlpha_MVP_Milestone_Implementation_Plan.md — sections 2 and 4 only, then the current task card
3. SESSION_HANDOFF.md — current state and continuation rules

State: M0-T01 is DONE and verified (see SESSION_HANDOFF.md §3).
Next task: M0-T02 (plan §6). Create docs/implementation/progress.md first and record M0-T01 as DONE with its actual verification results, then implement M0-T02 per its task card.

Constraints: one task per session; frozen contracts in plan §3; standard four checks must pass; do not commit; report BLOCKED per plan §2.5.
```

---

## 8. Source references (verified 2026-09-20)

1. Hermes upstream: https://github.com/NousResearch/hermes-agent (docs: https://hermes-agent.nousresearch.com/docs/)
2. AVO paper: https://arxiv.org/abs/2603.24517 · NVIDIA blog (Aug 2026): AVO ARC-AGI-3 architecture
3. DatedGPT (lookahead bias): https://arxiv.org/abs/2603.11838
4. TradingAgents changelog (v0.5.0, 2026-09-18): https://github.com/TauricResearch/TradingAgents/blob/main/CHANGELOG.md
5. SEC EDGAR fair access: https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data
6. Obsidian: Graph view / Properties / Bases (help.obsidian.md)
7. W3C PROV-O: https://www.w3.org/TR/prov-o/ · FIBO: https://spec.edmcouncil.org/fibo/
8. Ollama OpenAI compatibility (subset): https://docs.ollama.com/api/openai-compatibility
9. Streamlit forms: https://docs.streamlit.io/develop/concepts/architecture/forms
