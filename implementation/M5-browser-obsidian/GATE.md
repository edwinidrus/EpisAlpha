# Gate G5: browser workbench and Obsidian

**Status:** not started.

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

_No runs yet._
