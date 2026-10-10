# Gate G7: demo acceptance

**Status:** not started.

## Commands

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src/episalpha
uv run pytest -q -m "not live"
uv run python scripts/demo_smoke.py
set -a; . ./.env; set +a
uv run pytest -q -m live tests/integration/test_hermes_runtime.py tests/integration/test_runtime_boundary.py
uv run python scripts/diagnose.py
```

Final live checks require configured credentials and a runtime. Record BLOCKED if they are
unavailable; offline success is reported separately.

## Criteria

- [ ] Acceptance rows A01–A26 each have a passing test, or a recorded manual check, or BLOCKED
      with a reason.
- [ ] The smoke script passes from a clean checkout by following the README. Replay works with
      no network.
- [ ] Backup and restore work across DB, objects and runs, with hashes verified.
- [ ] Final walkthrough: a real-provider run, replay, source inspection, contradiction and
      unknowns, graph, export, the candidate comparison, and an intentional source or model
      failure.
- [ ] All G0–G7 outcomes are recorded. Definition of done (plan §15.1) is fully ticked or
      explicitly open.
- [ ] Final `DIAGNOSTICS.md` and the `diagnose.jsonl` trend are attached to the handoff.

## Results log (append-only; real output only)

_No runs yet._
