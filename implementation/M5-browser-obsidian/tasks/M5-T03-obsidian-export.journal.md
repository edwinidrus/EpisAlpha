# M5-T03 journal — Deterministic Obsidian exporter

## Attempt 1 — 2026-10-11 08:47 UTC — claude-opus-5-5
- Hypothesis: the notes can be rendered by pure string functions over M5-T02's `RunKnowledge`.
  A writer that compares each file against the previous manifest and the new content can then
  give a byte-stable, never-silently-overwriting vault.
- Did:
  - `src/episalpha/knowledge/export_obsidian.py` (new):
    - `render_notes` (pure), `export_knowledge`, `export_run`, `safe_name`.
    - Layout: `generated/<run_id>/{thesis,claims,spans,documents,hypotheses,relations}/<id>.md`
      plus `manifest.json`, and `annotations/`.
  - `src/episalpha/cli.py`: `export obsidian --run RUN_ID [--output PATH]`.
    - Default vault `<data_root>/exports/vault`.
    - Exit 2 for an unknown or unfinished run or an unwritable vault; 4 on an integrity error.
  - `apps/streamlit_app.py`: an "Export to Obsidian vault" button on the Knowledge tab, through
    the same `export_knowledge` (M5 article 10).
  - `src/episalpha/knowledge/query.py`: `RunKnowledge` gains `state` and `research_mode`;
    `derivation_chain` and `claim_passages` are now public.
  - Tests:
    - `tests/knowledge/test_obsidian_export.py` (20) and one UI test.
    - The SYNTHETIC `RunKnowledge` moved from `test_query.py` to
      `tests/fixtures/run_knowledge.py`; the real-run helpers moved to
      `tests/knowledge/conftest.py`. This replaces M5-T02's test-imports-test hack.
  - Docs: README status and Docker line; HANDOFF command and expected count.
- Decisions recorded, as the pack asks:
  - **Export time:** recorded nowhere, not even in `manifest.json`. The manifest carries the
    run's own `run_ended_at`, so the whole tree, manifest included, is byte-stable. The export
    span holds the wall-clock time.
  - **Conflict:** a generated file whose SHA-256 matches neither the previous manifest nor the
    new content counts as edited. So does a symlinked or non-file `manifest.json`. In either
    case the export goes to the first clean `generated/<run_id>.<n>/`. Exit 0, with every edited
    file listed. Re-exporting reuses the clean `.n`, so it stays idempotent. The "or the new
    content" rule keeps a crash before the manifest write from looking like an edit.
  - **Untrusted text** (statements, quotes, model text, source URIs, units) never goes in
    properties. It sits in a fence longer than any backtick run inside it, so Obsidian renders
    no HTML, links, embeds or tags from it.
  - **Links** are vault-relative with `.md` and an alias, `[[generated/<dir>/claims/<id>.md|<id>]]`.
    Without `.md`, dotted IDs read as attachment extensions. Without the full path, the same
    snapshot span ID exported for two runs would be ambiguous.
  - **Scope:** the thesis, all run and snapshot claims, hypotheses, recorded relations, and only
    the spans and documents they cite.
- Found in self-review and fixed, each with a test:
  1. Stale-file cleanup trusted names from the editable `manifest.json`. A tampered entry
     `../../annotations/mine.md` deleted a matching owner note inside the vault. A mutation
     check proved it: guard removed -> test FAIL; restored -> PASS. Cleanup now only deletes
     paths matching the generated-note pattern.
  2. A symlinked `manifest.json` was refused only after the notes were written. It is now a
     conflict up front.
- Ran:
  - `uv run pytest -q tests/knowledge/test_obsidian_export.py` before building -> collection
    error, `episalpha.knowledge.export_obsidian` missing (red, expected reason).
  - Same command after building -> `20 passed`. `uv run pytest -q tests/knowledge tests/ui` ->
    all passed.
  - Four checks: ruff clean, format clean, mypy clean (the app was checked too);
    `606 passed, 8 deselected`.
  - `uv run python scripts/diagnose.py` -> `diagnose: PASS | tests {'passed': 606, ...} |
    failures 0 | regressions 0 | orphans 0`.
  - Pack command on the fake run `run-580ea8734b14` (scratch data root), run twice as separate
    processes, the second with `PYTHONHASHSEED=12345`:
    `find generated -type f | sort | xargs sha256sum | sha256sum` ->
    `4babdb166ff407235c2f006d51b3e4cd0684dde752a1efd6db72750df726398d` both times (identical).
    9 files; manifest `ba0243e040b1f55f026a0c6dfb8b846aeb35b7987fdef6aac5cf791bf486a1c8`.
  - Conflict smoke: appended an edit to `claims/run-580ea8734b14.c1.md` and wrote
    `annotations/mine.md`, then exported again ->
    `exported: ... -> generated/run-580ea8734b14.2`, `conflicts: 1`, exit 0. The edit and the
    annotation were intact. 88 links in the vault, 0 unresolved.
  - Span from `spans.jsonl`: `export.obsidian {episalpha.run_id, episalpha.destination:
    generated/run-580ea8734b14.2, episalpha.files: 9, episalpha.manifest_hash: bc8e74...,
    episalpha.conflicts: 1, outcome: ok}`. No evidence text, no absolute path.
- Outcome: PASS
- Not done: opening the vault in the Obsidian app. That is the M5-T04 owner check ("Obsidian
  opens exported vault with working local links").
- Diagnose: PASS, 0 regressions; expected span `export.obsidian` seen (`spans.jsonl`).
