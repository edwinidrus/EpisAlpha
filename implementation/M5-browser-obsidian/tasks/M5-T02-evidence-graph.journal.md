# M5-T02 journal — Evidence inspection and local graph

## Attempt 1 — 2026-10-11 08:34 UTC — claude-opus-5-5
- Hypothesis: one load through the hash-verified replay, then pure functions over the run's
  records, gives a drilldown, relation table and graph that cannot show anything outside the
  run's snapshot or records.
- Did:
  - `src/episalpha/knowledge/query.py` (new): `load_run` -> `RunKnowledge` (the run's records
    plus the manifest's documents, permitted spans, claims and relations, instruments and their
    issuers, current assessments); `assertion_drilldown`, `relation_table`,
    `local_graph(..., limit)`, `to_dot`.
  - `src/episalpha/knowledge/__init__.py` (new, docstring only).
  - `apps/streamlit_app.py`: Evidence tab (assertion selectbox -> claims with epistemic and
    review badges, six clocks, contradictions, derivation chain, passages via `st.code`) and
    Knowledge tab (relation table first, then `st.graphviz_chart` in a try block).
  - `src/episalpha/settings.py` + `config/demo.example.toml`: `limits.max_graph_nodes`
    (default 50, max 50). Global article 21 keeps all limits there, so it replaces the pack's
    `limit=50` default.
  - Tests: `tests/knowledge/test_query.py` (12), 3 UI tests added to
    `tests/ui/test_research_view.py`.
- Deviations from the pack, all deliberate:
  - The functions take a loaded `RunKnowledge`, not a `run_id`. Loading once keeps them pure
    and testable without a database.
  - The runner stores only `CONTRADICTS` relations. So the table also shows edges implied by
    record fields, using frozen predicates with valid endpoints: `HAS_SPAN`, `REPORTS`, `ABOUT`,
    hypothesis `SUPPORTS`/`CONTRADICTS`. Each row carries its `origin`, so recorded and implied
    edges stay distinguishable.
  - Two lowercase labels, `cites` (thesis -> record) and `derivation input`, are references,
    not relations. Claim->claim derivation edges have no predicate in the vocabulary, and adding
    one needs owner approval.
  - A derived claim's passages are those of its inputs, found recursively.
  - Runs whose records were REJECTED are shown with a "never persisted" warning.
- Ran:
  - `uv run pytest -q tests/knowledge/test_query.py` before building ->
    `ModuleNotFoundError: No module named 'episalpha.knowledge'` (red, expected reason).
  - Same command after building -> `12 passed`.
  - `uv run pytest -q tests/knowledge tests/ui` -> `30 passed`.
  - Four checks: ruff clean, format clean, mypy clean (`uv run mypy src/episalpha
    apps/streamlit_app.py` also clean); `585 passed, 8 deselected`.
  - `uv run python scripts/diagnose.py` -> `diagnose: PASS | tests {'passed': 585, ...} |
    failures 0 | regressions 0 | orphans 0`.
  - Smoke, scratch data root, fake runtime: `research run --case supported` ->
    `run-580ea8734b14`. Drilldown of the first assertion -> `run-580ea8734b14.c1`,
    passage `'Fourth quarter revenue reached EUR 412.0 million. Ma'`. Graph: 8 nodes, 12 edges,
    not truncated. `streamlit run --server.port 8598` -> health `ok`, `LISTEN 127.0.0.1:8598`
    only.
- Outcome: PASS
- Click count from assertion to passage: counted from the page structure, not a manual browser
  run. The Research tab selects the run. Then 1 click (Evidence tab) shows the first assertion's
  claims and passages, and 2 more clicks (open the selectbox, pick) reach any other assertion.
  The owner measures it in the M5-T04 walkthrough.
- Decision: no new spans. Loading goes through `replay`, which already emits a `replay` span.
  M5 article 10 asks for spans on submit, cancel and export only.
- Diagnose: PASS, 0 regressions; expected spans: none new for this task (`replay` per load).
