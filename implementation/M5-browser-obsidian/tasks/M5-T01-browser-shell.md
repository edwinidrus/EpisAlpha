# M5-T01 — Browser shell and research view

| Field | Value |
|---|---|
| Status | TODO |
| Depends on | G4 |
| Phase constitution | [../CONSTITUTION.md](../CONSTITUTION.md) (inherits [global](../../CONSTITUTION.md)) |
| Plan source | plan §11 M5-T01 card, §3.6 "Background execution"; acceptance rows A11, A22, A23 |
| Journal | `tasks/M5-T01-browser-shell.journal.md` |

## 0. Context to load

Load these and nothing else:
- `implementation/CONSTITUTION.md`
- `implementation/M5-browser-obsidian/CONSTITUTION.md`, articles 1–3 and 9
- `src/episalpha/research/runner.py`: `admit`, `request_cancel`, and the status reads
- `src/episalpha/cli.py`, `research execute` (the worker entry point the UI launches)
- `src/episalpha/contracts/research.py`: `RunRecord`, `RunState`, `Thesis.limitation_notice`

> Browser submission persists a job and launches a dedicated trusted runner subprocess once;
> page reruns only read status. (plan §3.6)

## 1. Plan

- **Goal:** a localhost Streamlit app with four tabs (Research, Evidence, Knowledge,
  Experiments). Research is functional; the others are explicit placeholders. Submitting starts
  exactly one job, and every rerun only reads state.
- **Files:**
  - `apps/streamlit_app.py`
  - A shared application service only if one already exists and is required
  - `pyproject.toml` / `uv.lock`, to add `streamlit`
  - Focused test: `tests/ui/test_research_view.py` (Streamlit `AppTest`, with fake services)
- **Build:**
  - Use `st.form` for submission. On submit, call `admit()` with a deterministic idempotency key
    from (case or snapshot, question, runtime, form nonce stored in `st.session_state`). Then
    launch `episalpha research execute RUN_ID` **once**, as a detached subprocess.
  - The status panel shows:
    - the state badge;
    - the terminal reason;
    - a cancel button that calls `request_cancel`;
    - model ID and `served_by`, and the harness hash;
    - elapsed time;
    - usage, where unknown is shown as "unknown";
    - the `[FIXTURE]` or `LIVE` label, and the saved-replay label;
    - the retrospective notice in historical mode;
    - an **"Open trace in Phoenix"** link from `trace_url(trace_id)`, shown only when Phoenix
      is configured (A14).
  - The thesis is rendered from `ThesisAssertion`s only, with their status chips.
- **Out of scope:** the evidence drilldown (M5-T02), export (M5-T03), and the Experiments tab
  content (M6-T04).
- **Do not:**
  - Call the runtime or relay from the render path.
  - Store run state only in `session_state`. Persistence is the source of truth.

## 2. Verify (before building)

- [ ] G4 has passed.
- [ ] `uv add streamlit` resolves. Journal the version. Confirm that `streamlit.testing.v1.AppTest`
      exists in that version.
- [ ] Baseline: the four checks and `diagnose.py` are green.
- [ ] **Red first.** Write `test_research_view.py` with a fake admission service that counts
      calls. Cover:
  - Submit, then rerun 3 times, then switch tabs: exactly 1 admission and 1 launch.
  - Each state renders its badge (running, failed, partial, abstained, rejected, completed).
  - The cancel button calls `request_cancel`.
  - Unknown usage is shown as "unknown", never 0.
  - The fixture label is shown for fake runs.

## 3. Build

1. Write the app skeleton and tabs.
2. Write the form, idempotent admission, and the single launch.
3. Write the status polling, using `st.rerun` on a timer or a manual refresh button. Choose the
   simpler one and record why.
4. Write the thesis rendering from assertions.

## 4. Test

```bash
uv run pytest -q tests/ui/test_research_view.py
uv run streamlit run apps/streamlit_app.py --server.address 127.0.0.1   # manual smoke
uv run ruff check . && uv run ruff format --check . && uv run mypy src/episalpha && uv run pytest -q -m "not live"
```

Acceptance:
- [ ] Page reruns, tab changes and browser refresh do not duplicate a research job.
- [ ] The user sees running, failed, partial and abstained status, the cancel action, model and
      harness, elapsed time, and the saved-replay or live labels.

## 5. Diagnose

- [ ] `diagnose.py`: no regression; `tests/ui` appears.
- [ ] A manual smoke with a fake run shows one `ui.submit` → `research.run` trace per submit, in
      `spans.jsonl` or Phoenix.
      Paste it in the journal.

## 6. Stop and hand off

- **BLOCKED if:** `AppTest` is unavailable in the resolved Streamlit version, and no
  alternative test approach fits inside the file budget.
- **Record:** M5 `PROGRESS.md`, `STATUS.md`, and the journal.
- **Next:** M5-T02.
