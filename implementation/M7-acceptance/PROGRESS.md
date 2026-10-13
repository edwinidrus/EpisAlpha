# M7 progress

One row per task. A task is DONE only when its acceptance checks actually pass, with the real
command output recorded here. Keep `../STATUS.md` in step. Commits are an owner action.

| Task | Status | Changes | Verification | Blocker | Next |
|---|---|---|---|---|---|
| M7-T01 | DONE | `tests/integration/test_demo_acceptance.py`: 30 tests, A01–A29 + A32, each across a real boundary (CLI, services, AppTest, relay HTTP front, worker files, exporter, campaign); row-to-test map in the journal; no production change | `uv run pytest -q tests/integration/test_demo_acceptance.py` -> `30 passed` (first run 25/5, all five test-side errors); four checks green; `diagnose.py` -> `PASS | tests {'passed': 729, ...} | regressions 0 | orphans 0` | Manual/live parts listed in M7 `GATE.md` | M7-T02 |
| M7-T02 | DONE | `scripts/demo_smoke.py` (temporary state; seed, 3 fake cases, offline replays, export + link scan, fake campaign, DB/objects/runs backup+restore with hash manifest, replay from restore; `--inject-failure`); `tests/integration/test_smoke_script.py` (2); README quick start; config template; `docs/implementation/demo_acceptance.md` | red: `2 failed`; smoke -> `smoke: PASS`, replay after warm-up 0.30 s, total 4.7 s; clean-copy rehearsal PASS; four checks green; `diagnose.py` -> `PASS | tests {'passed': 731, ...} | regressions 0` | None (a literal `git clone` rehearsal needs the work committed) | M7-T03 |
| M7-T03 | BLOCKED | Offline part only: G7 automated results with machine and versions in `GATE.md`; `demo_acceptance.md`; handoff section in `docs/implementation/progress.md` (follow-on work named, not started) | smoke PASS; four checks green; `diagnose.py` -> `PASS | tests {'passed': 731, ...}`; live commands not run | Owner present + live-call approval for: a real-provider run, the M6 live campaign, intentional live failures, browser refresh, Obsidian check | none in v0.1 |
