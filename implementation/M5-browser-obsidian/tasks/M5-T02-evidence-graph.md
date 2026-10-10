# M5-T02 — Evidence inspection and local graph

| Field | Value |
|---|---|
| Status | TODO |
| Depends on | M5-T01 |
| Phase constitution | [../CONSTITUTION.md](../CONSTITUTION.md) (inherits [global](../../CONSTITUTION.md)) |
| Plan source | plan §11 M5-T02 card, §3.4; A8; acceptance rows A02, A14, A21 |
| Journal | `tasks/M5-T02-evidence-graph.journal.md` |

## 0. Context to load

Load these and nothing else:
- `implementation/CONSTITUTION.md`
- `implementation/M5-browser-obsidian/CONSTITUTION.md`, articles 3–5
- `apps/streamlit_app.py` (M5-T01)
- `src/episalpha/research/artifacts.py`, which reads a run's records
- `src/episalpha/storage/repository.py`: `relations_from`, `get_span`, `current_assessment`
- `src/episalpha/research/derivations.py`, `REGISTRY`, to label method versions
- `src/episalpha/contracts/knowledge.py`: `RelationPredicate`, `Claim`, `NumericFact`,
  `Derivation`

## 1. Plan

- **Goal:** from any thesis assertion, a user drills down to its claim, then its span, then the
  original passage. For a numeric claim, the drilldown shows the derivation chain. A run-scoped
  graph of up to 50 nodes and a relation table show how the evidence connects.
- **Files:**
  - `src/episalpha/knowledge/query.py`
  - `apps/streamlit_app.py`
  - Focused test: `tests/knowledge/test_query.py`, plus a small UI test extension if needed
- **Produces, in `query.py`** (pure functions over the run's records):
  - `assertion_drilldown(run_id, assertion_id) -> Drilldown`, carrying claims, spans, passages,
    timestamps (all six clocks where present), semantic status, and the derivation chain. The
    chain is `{inputs: [(claim_id, value, unit, period)], method, method_version, value}`.
  - `relation_table(run_id) -> list[RelationRow]`.
  - `local_graph(run_id, center_id, limit=50) -> Graph`, with typed nodes and edges labelled by
    predicate. Breadth-first from the selected thesis, truncated at `limit`, with the truncation
    flagged.
- **UI:**
  - The Evidence tab uses `st.text` or `st.code` for passages, never `unsafe_allow_html`.
  - The Knowledge tab shows the relation table first, then the graph through
    `st.graphviz_chart` from generated DOT text, with node labels escaped.
- **Do not:**
  - Query outside the run's snapshot and records.
  - Render model or source text as HTML.

## 2. Verify (before building)

- [ ] The artifact reader exposes the run's records, as the M4-T01 journal shows.
- [ ] Baseline: the four checks and `diagnose.py` are green.
- [ ] **Red first.** Write `test_query.py`. Cover:
  - The drilldown resolves for a reported claim and for a derived claim, with the chain values
    matching `recompute`.
  - A node from another run never appears.
  - The 50-node cap is applied, with truncation flagged.
  - `CONTRADICTS` edges are present for the conflicting fixture.
  - Common lineage is visible for copied sources (A21).
  - An HTML or script payload in a passage is returned as an inert string, and the UI test
    asserts it is not rendered as HTML.

## 3. Build

1. Write the pure query functions.
2. Write the Evidence tab drilldown.
3. Write the Knowledge tab table and DOT graph.

## 4. Test

```bash
uv run pytest -q tests/knowledge/test_query.py tests/ui
uv run ruff check . && uv run ruff format --check . && uv run mypy src/episalpha && uv run pytest -q -m "not live"
```

Acceptance:
- [ ] Every displayed node and edge belongs to the selected snapshot or run.
- [ ] Unsupported status is visible.
- [ ] Source text is rendered safely.
- [ ] The graph limits are bounded.
- [ ] The relation table stays usable if the graphical layout fails.
- [ ] The derivation chain is shown for numeric claims (A8).

## 5. Diagnose

- [ ] `diagnose.py`: no regression.
- [ ] The journal records the click count from assertion to passage, measured manually.

## 6. Stop and hand off

- **BLOCKED if:** run records lack the relation or derivation data. Trace it to the responsible
  earlier task.
- **Record:** M5 `PROGRESS.md`, `STATUS.md`, and the journal.
- **Next:** M5-T03.
