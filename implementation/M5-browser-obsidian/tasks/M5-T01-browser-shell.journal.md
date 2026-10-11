# M5-T01 journal

## Attempt 1 — 2026-10-11 09:00 UTC — claude-opus-5-5
- Gate: G4 is PARTIAL (offline passed; M4-T04 real-case reviews blocked on the G2 owner
  checkpoint). The owner said on 2026-10-11 "please proceed the further milestones" after the
  M4 report, which is recorded in `docs/implementation/progress.md` as the go-ahead.
- Verify:
  - Baseline: four checks green, `553 passed, 8 deselected`.
  - `uv add "streamlit>=1.40,<2.0"` resolved **streamlit 1.65.0**; `streamlit.testing.v1.AppTest`
    exists (also `st.badge`, `st.fragment(run_every=)`, `st.link_button`). `st.text` is
    "Write text without Markdown or HTML parsing" in this version: it is the untrusted-text path.
  - Red first: `tests/ui/test_research_view.py` written first -> `12 failed, 3 errors`
    (missing app and services functions).
- Did:
  - `apps/streamlit_app.py`: Research / Evidence / Knowledge / Experiments tabs. `st.form`
    submit with a per-session nonce in the idempotency source; admission through
    `services.submit`; worker launch through `services.launch`, guarded by an exclusively
    created `runs/<run_id>/launch.json`, so the guard lives in persistence, not the session.
    Status panel: state badge, reason, error code, warnings, FIXTURE or LIVE label, the
    retrospective notice, model, served_by, harness and hash, elapsed, usage ("recorded when
    the run ends" while active; "unknown" tokens and cost), "Open trace in Phoenix" only when
    configured, cancel button, stage-attempt table, saved-replay label (artifacts verified) or
    the `INTEGRITY_ERROR`. Thesis rendered only from `ThesisAssertion`s, by section, with chips
    "record · epistemic status · review status". Model text goes through `st.text`; Markdown
    widgets only show escaped app-generated labels.
  - Polling: `st.fragment(run_every=2)` only while the selected run is active (the fragment
    re-reads persistence; no loop, no session state). Chosen over a manual refresh button: it
    is one native call and needs no user action; it stops by a full rerun when the run ends.
  - `.streamlit/config.toml`: `server.address = 127.0.0.1`, headless, `gatherUsageStats=false`.
  - `services.py`: `plan_case` / `plan_snapshot` (moved out of the CLI so the CLI and the UI
    build requests the same way; CLI idempotency keys unchanged), `launch`, `_spawn`,
    `recent_runs`, `run_view` / `RunView`, `usage_line` (also used by the CLI).
  - `cli.py`: uses the shared planners and `usage_line`; `python -m episalpha.cli` works.
  - `runner.py` + `hermes.py`: `served_by` recorded in the run index (it was only in spans,
    which application logic must not read).
- **Bugs found and fixed (both with red-first regression tests):**
  1. A Hermes run whose runtime could not start (credential not exported, no worker) was
     admitted and claimed, then stayed QUEUED forever, holding v0.1's single job slot: every
     later admission was refused. Proven red against the HEAD code (`assert 2 == 0`). Now
     `services.submit` checks Hermes readiness before admitting a new run.
     Test: `test_a_hermes_run_that_cannot_start_is_refused_before_admission`.
  2. `Repository.run_usage` summed token counts with SQL `SUM`, which skips NULLs: one
     unreported attempt turned "unknown" into a smaller number (constitution article 13).
     Test: `test_usage_tokens_stay_unknown_when_any_attempt_did_not_report_them`.
- Scope note: 5 implementation files instead of 1–3. Two are one-line additions (`served_by`),
  `cli.py` is a net deletion (shared planners), `repository.py` is the bug fix above. Splitting
  them out would have left the UI duplicating admission logic.
- Ran:
  - `uv run pytest -q tests/ui/test_research_view.py` -> `15 passed`.
  - `uv run mypy src/episalpha apps/streamlit_app.py` -> `Success: no issues found in 36
    source files` (the gate checks `src/episalpha` only; the app was checked too).
  - Four checks: ruff clean, format clean, mypy clean, `570 passed, 8 deselected`.
  - `uv run python scripts/diagnose.py` -> `diagnose: PASS | tests {'passed': 570, ...} |
    failures 0 | regressions 0 | orphans 0`; `tests/ui` appears with 15.
- Manual smoke (scratch data root, fake runtime, real detached worker launched by the app):
  ```text
  run run-77876d2a6905 state RESEARCH_COMPLETED
  badge [':green-badge[Completed]']
  research.run 5b3cca60fe345bc70f594a707c8a9d25 run run-77876d2a6905 session run-77876d2a6905
  ui.submit    daf5392d709ee8e19c955797709205ca run run-77876d2a6905 session run-77876d2a6905 launched True
  launch marker: True
  worker.log: [FIXTURE] fake runtime: scripted fixture output, not research
  ```
  `uv run streamlit run apps/streamlit_app.py --server.port 8599` ->
  `LISTEN 127.0.0.1:8599`, `/_stcore/health` -> `ok`. Browser click-through itself was not
  performed by the model (that is the M5-T04 owner walkthrough).
- Not done: during a run the Phoenix link appears only after the run ends (the runner writes
  `trace_id` into the index at finish).
- Result: DONE. Next: M5-T02.
