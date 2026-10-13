# Gate G5: browser workbench and Obsidian

**Status:** PARTIAL (2026-10-12): automated criteria passed; the two manual owner checks are open.

## Commands

```bash
uv run streamlit run apps/streamlit_app.py --server.address 127.0.0.1
uv run pytest -q tests/ui tests/knowledge
uv run python scripts/diagnose.py
# plus the four standard checks
```

## Criteria

- [ ] Refresh, rerun and tab change never duplicate a job or spend model requests (A11).
- [ ] Status, cancel, model and harness, elapsed time, and the replay or live label are visible.
- [ ] Assertion to claim to span drilldown, with the derivation chain for numeric claims (A8),
      unsupported status visible, and safe rendering.
- [ ] Graph limited to 50 nodes, scoped to the run; the relation table works on its own.
- [ ] The Obsidian export is byte-stable, all links resolve, annotations are preserved, and
      there is no path traversal.
- [ ] Manual check: the owner reaches the original passage from an assertion in 3 deliberate
      clicks or fewer.
- [ ] Manual check: Obsidian opens the vault and the local links work.
- [ ] UI and export actions are visible as spans (`ui.*`, `export.obsidian`), with Phoenix trace
      links on runs.

## Results log (append-only; real output only)

### 2026-10-12 — automated part (claude-opus-5-5), after M5-T04

- `uv run pytest -q tests/ui tests/knowledge` -> `56 passed`.
- Four checks: `ruff check` all passed; `ruff format --check` 84 files formatted; `mypy
  src/episalpha` no issues in 38 files; suite inside diagnose 637 passed.
- `uv run python scripts/diagnose.py` -> `diagnose: PASS | tests {'passed': 637, 'failed': 0,
  'errors': 0, 'skipped': 0} | failures 0 | regressions 0 | orphans 0 | 48.3s`.
- Real Streamlit (`--server.port 8597`, 127.0.0.1), headless Chromium, [FIXTURE] run
  `run-3b0fc0f7b665`: status, model, harness, elapsed, replay label and FIXTURE label visible;
  drilldown with six clocks and review badges; relation table + graph; export button ->
  `Exported 9 files to generated/run-3b0fc0f7b665`; vault link scan `links 44 unresolved 0`.

| Criterion | Result |
|---|---|
| Refresh/rerun/tab change never duplicate a job | PASS (`tests/ui/test_research_view.py`) |
| Status, cancel, model/harness, elapsed, replay/live label | PASS (tests + browser) |
| Drilldown, A8 chain, unsupported visible, safe rendering | PASS (`tests/knowledge/test_query.py`, UI tests) |
| Graph ≤ 50 nodes, run-scoped; table works alone | PASS (tests) |
| Export byte-stable, links resolve, annotations kept, no traversal | PASS (`test_obsidian_export.py`; link scan) |
| UI/export spans | PASS (`test_submit_and_cancel_emit_ui_spans`, M5-T03 span record) |
| **Manual:** owner reaches passage in ≤ 3 clicks | OPEN — model's browser count is 3; owner's own count pending |
| **Manual:** Obsidian opens the vault, local links work | OPEN — needs the owner and the Obsidian app |

