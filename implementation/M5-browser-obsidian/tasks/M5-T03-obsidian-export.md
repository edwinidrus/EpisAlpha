# M5-T03 — Deterministic Obsidian exporter

| Field | Value |
|---|---|
| Status | TODO |
| Depends on | M5-T02 |
| Phase constitution | [../CONSTITUTION.md](../CONSTITUTION.md) (inherits [global](../../CONSTITUTION.md)) |
| Plan source | plan §11 M5-T03 card; acceptance row A15 |
| Journal | `tasks/M5-T03-obsidian-export.journal.md` |

## 0. Context to load

Load these and nothing else:
- `implementation/CONSTITUTION.md`
- `implementation/M5-browser-obsidian/CONSTITUTION.md`, articles 6–8 and 10
- `src/episalpha/knowledge/query.py` (M5-T02), the data source for notes
- `src/episalpha/cli.py`, where the command is added
- `src/episalpha/observability.py`, where `EXPORT_COMPLETED` is added to `EventName`

**The command:**

```bash
uv run episalpha export obsidian --run RUN_ID --output .episalpha/exports/vault
```

## 1. Plan

- **Goal:** a one-way, byte-stable Markdown vault for one run. It has safe filenames, resolvable
  links and an export manifest, and it never touches user annotations.
- **Files:**
  - `src/episalpha/knowledge/export_obsidian.py`
  - `src/episalpha/cli.py`
  - Focused test: `tests/knowledge/test_obsidian_export.py`
- **Layout:**
  - `vault/generated/<run_id>/{thesis,claims,spans,documents,hypotheses,relations}/<stable_id>.md`
  - `vault/generated/<run_id>/manifest.json`, with each file's SHA-256
  - `vault/annotations/`, created once and never written again
- **Note format:**
  - YAML front matter of flat properties: id, kind, status, `epistemic_status`, run, snapshot
    hash, timestamps with offsets.
  - Body: the quote or statement, the source locator, and quoted `[[links]]` by stable ID.
- **Determinism:**
  - Sorted keys and sorted lists.
  - `\n` line endings.
  - No export timestamp in the note bodies. The export time lives only in `manifest.json`, which
    is itself compared ignoring that field. Alternatively, derive it from the run record. Choose
    one and record it.
- **Conflict:** if any existing `generated/<run_id>` file's hash differs from the previous
  manifest, the user edited it. Then refuse with exit 2 and a message, or write to a new
  `generated/<run_id>.<n>/`. Never overwrite silently.
- **Do not:**
  - Use titles or model text in filenames.
  - Use community plugins.
  - Import notes back.

## 2. Verify (before building)

- [ ] `query.py` gives everything the notes need.
- [ ] Baseline: the four checks and `diagnose.py` are green.
- [ ] **Red first.** Write `test_obsidian_export.py`. Cover:
  - Only the selected run is exported.
  - All `[[links]]` resolve to existing files.
  - Two exports give byte-identical files.
  - An ID containing `../` is impossible, and a test proves no path escapes the vault.
  - A file in `annotations/` is untouched.
  - A modified generated file gives a conflict or a new destination.
  - An `export.completed` event is emitted.

## 3. Build

1. Write the note renderers, as pure string functions.
2. Write the writer, which builds the manifest, checks for conflicts, and writes atomically.
3. Write the CLI command.

## 4. Test

```bash
uv run pytest -q tests/knowledge/test_obsidian_export.py
uv run episalpha export obsidian --run <fake-run-id> --output .episalpha/exports/vault
uv run ruff check . && uv run ruff format --check . && uv run mypy src/episalpha && uv run pytest -q -m "not live"
```

Acceptance:
- [ ] Only the selected run's records are exported.
- [ ] All generated links resolve.
- [ ] A repeated unchanged export is byte-stable.
- [ ] Filenames cannot traverse paths.
- [ ] User notes are untouched.
- [ ] A modified generated file causes a conflict or a new destination.

## 5. Diagnose

- [ ] `diagnose.py`: no regression.
- [ ] The journal records the `sha256sum` of two consecutive exports, which must be identical.

## 6. Stop and hand off

- **Record:** M5 `PROGRESS.md`, `STATUS.md`, and the journal.
- **Next:** M5-T04.
