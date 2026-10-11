# M5 plan: browser workbench and Obsidian

**Goal:** reasoning and its limitations are inspectable in a browser, with minimal frontend
complexity, and the evidence graph exports to Obsidian deterministically.

**Plan source:** plan §11 (M5-T01..T04); A8 (derivation chain); acceptance rows A02, A11, A14,
A15, A21, A22, A23.

## Tasks

| Task | Title | Status | Depends on | Pack |
|---|---|---|---|---|
| M5-T01 | Browser shell and research view | DONE | G4 | [pack](tasks/M5-T01-browser-shell.md) |
| M5-T02 | Evidence inspection and local graph | TODO | M5-T01 | [pack](tasks/M5-T02-evidence-graph.md) |
| M5-T03 | Deterministic Obsidian exporter | TODO | M5-T02 | [pack](tasks/M5-T03-obsidian-export.md) |
| M5-T04 | Browser walkthrough and usability correction | TODO | M5-T03 | [pack](tasks/M5-T04-walkthrough.md) |

## Dependencies

- `streamlit` is in the plan's allowed runtime set (plan §4.2) but is **not yet** in
  `pyproject.toml`. M5-T01 adds it, using `uv add streamlit`, and records the locked version.
- Graph rendering: try Streamlit-native means first (a table plus `st.graphviz_chart`, which
  takes DOT text). Add a graph library only if a task proves it necessary, and record why.

## Out of scope

Experiments tab content (M6-T04), remote hosting, authentication, bidirectional Obsidian sync,
community plugins.
