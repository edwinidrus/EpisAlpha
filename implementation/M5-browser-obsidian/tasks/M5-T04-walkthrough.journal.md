# M5-T04 journal — Browser walkthrough and usability correction

## Attempt 1 — 2026-10-12 20:00 UTC — claude-opus-5-5
- Hypothesis: the six-step walkthrough, performed in a real browser by the model acting as the
  user, surfaces the rough edges; each gets a red test first and a narrow fix.
- Setup: scratch data root, `demo seed`, `research run --case conflicting` ->
  `run-3b0fc0f7b665` `RESEARCH_COMPLETED` [FIXTURE]; `streamlit run --server.port 8597`;
  headless Chromium driven by Playwright (scratch tool outside the repo, not a dependency),
  full-page screenshots per step.
- Walkthrough findings, recorded before any fix:
  1. **Inspect a quote:** passages were cut mid-word: "Fourth quarter revenue reached EUR 412.0
     million. Ma" and "agement expects demand to soften during the first half." The demo corpus
     spans had offsets 0..52 and 53..108; the sentences are 0..49 and 50..108. Offsets and
     quotes agreed, so the contract passed, but the citation reads broken. The same offsets were
     in `tests/fixtures/synthetic_knowledge.py`, and two tests pinned the cut quote.
  2. **Status panel:** `harness: harness.baseline hash recorded wh`. The fallback sentence was
     sliced with the hash (`[:16]`), and a fixture run never gets a harness hash, so the line
     promised something that never comes.
  3. **Export:** paths in code spans showed Markdown escapes: `` `/tmp/claude\-1000/\-home…` ``
     and `` `generated/run\-3b0f…` ``. Escapes are not processed inside a code span, so the
     displayed path does not exist when copied. The `research recover` hint had the same defect.
  - Not a defect: the thesis lists two similar `missing:` lines (critic and synthesizer wording
    differ; dedup is exact). Fixture text, left as is.
- Red first: `tests/ui/test_workbench.py` (5 tests).
  - Against the original corpus and app: `3 failed, 2 passed` — `assert 'Management expects…' in
    ['agement expects…']`, `'harness: har...h recorded wh' == 'harness: har...one (fixture)'`,
    corpus quote does not end a sentence. (The navigation and missing-information tests pass:
    those behaviours already worked.)
  - Code-span test added after finding 3: `1 failed` —
    `'` /tmp/pytest-of-…/vault `' in 'One-way export to `/tmp/pytest\\-of\\-…'`.
- Did:
  - `eval_cases/demo/synthetic_corpus.json`: span offsets 0..49 and 50..108, whole sentences.
  - `tests/fixtures/synthetic_knowledge.py`: same offsets.
  - `tests/ui/test_research_view.py`, `tests/knowledge/test_obsidian_export.py`: the pinned quote
    is now the whole sentence (same assertion, exact match; it had encoded the defect).
  - `apps/streamlit_app.py`: harness line shows the hash, else `none (fixture)`, `unknown` once
    finished, or "hash recorded when the run ends" while running; `code()` builds literal inline
    code spans (fence longer than any backtick run) for the vault path, the export destination
    and the recover command.
  - `docs/implementation/demo_script.md`: steps, expected screens, timing.
- Ran:
  - `uv run pytest -q tests/ui tests/knowledge` -> `56 passed`.
  - Four checks: ruff clean, `84 files already formatted`, mypy `Success: no issues found in 38
    source files` (`apps/streamlit_app.py` also clean); full suite inside diagnose: 637 passed.
  - `uv run python scripts/diagnose.py` -> `diagnose: PASS | tests {'passed': 637, 'failed': 0,
    'errors': 0, 'skipped': 0} | failures 0 | regressions 0 | orphans 0 | 48.3s`.
  - Browser re-run after the fixes: passage reads "Management expects demand to soften during the
    first half."; harness line `none (fixture)`; vault path and `generated/run-3b0fc0f7b665`
    shown without backslashes.
  - `episalpha replay run-3b0fc0f7b665` -> `8 artifacts verified, no model or network calls`.
  - Vault link check (script over every `[[target` in the exported vault): `files 8 links 44
    unresolved 0`.
- Click count, assertion to passage, measured in the browser: Evidence tab (1), open Assertion
  (2), pick *interpretation* (3) -> passage visible. The first assertion needs 1 click.
- Outcome: DONE_OFFLINE. Automated acceptance passes.
- Not done (owner): open the vault in the Obsidian app and record date and version; the owner's
  own click count. The model's browser run is not the owner walkthrough.
- Diagnose: PASS, 0 regressions; no new spans (UI actions unchanged; `export.obsidian` emitted by
  the export click as before).
