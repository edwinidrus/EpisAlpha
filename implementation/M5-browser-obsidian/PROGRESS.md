# M5 progress

One row per task. A task is DONE only when its acceptance checks actually pass, with the real
command output recorded here. Keep `../STATUS.md` in step. Commits are an owner action.

| Task | Status | Changes | Verification | Blocker | Next |
|---|---|---|---|---|---|
| M5-T01 | DONE | `apps/streamlit_app.py` (4 tabs; Research functional, others explicit placeholders), `.streamlit/config.toml` (127.0.0.1, usage stats off), `services.py` (`plan_case`/`plan_snapshot` shared with the CLI, `launch` once via exclusive `launch.json`, `recent_runs`, `run_view`, `usage_line`, Hermes readiness checked before admission), `runner.py` + `hermes.py` (`served_by` in the run index), `repository.run_usage` (unknown tokens stay unknown), streamlit 1.65.0 added | `uv run pytest -q tests/ui/test_research_view.py` -> `15 passed`; four checks green, `570 passed, 8 deselected`; `diagnose.py` -> `PASS ... failures 0 | regressions 0 | orphans 0`, `ui` 15; smoke: real detached worker -> `RESEARCH_COMPLETED`, one `ui.submit` + one `research.run` trace sharing `session.id`; `streamlit run` listens on `127.0.0.1:8599` only | None | M5-T02 |
| M5-T02 | TODO | Planned; see pack | — | — | M5-T03 |
| M5-T03 | TODO | Planned; see pack | — | — | M5-T04 |
| M5-T04 | TODO | Planned; see pack | — | — | G5 |
