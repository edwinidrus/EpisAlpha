# Gate G7: demo acceptance

**Status:** PARTIAL (2026-10-13): every automated criterion passes offline; the final owner walkthrough with live calls (M7-T03) is BLOCKED on the owner.

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

- [ ] Acceptance rows A01–A29 and A32 each have a passing test, or a recorded manual check, or BLOCKED
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

### 2026-10-13 — automated part (claude-opus-5-5)

Machine: WSL2 2.4.13.0, kernel 5.15.167.4-microsoft-standard-WSL2, x86_64; Python 3.12.3;
Streamlit 1.65.0, Pydantic 2.13.5, Typer 0.27.2; Hermes pin `c1488ac` (0.21.3); research
model route `nvidia/nemotron-3-ultra-550b-a55b:free` (config only; no live call this session).

- Four checks: `ruff check` all passed; `ruff format --check` 98 files formatted; `mypy
  src/episalpha` no issues in 45 files; `pytest -m "not live"` 731 passed.
- `uv run python scripts/demo_smoke.py` -> `smoke: PASS` (replay after warm-up 0.30 s, total
  4.7 s); clean-copy rehearsal -> `smoke: PASS` (0.28 s, 4.7 s).
- `uv run python scripts/diagnose.py` -> `PASS | tests {'passed': 731, ...} | failures 0 |
  regressions 0 | orphans 0`.
- Live commands (`pytest -m live tests/integration/test_hermes_runtime.py
  tests/integration/test_runtime_boundary.py`): **not run**: no owner approval for live calls in
  this session. BLOCKED, not skipped-as-pass.

| Criterion | Result |
|---|---|
| A01–A29 + A32: test, manual check or BLOCKED | PASS: 30 automated (`test_demo_acceptance.py`); manual/live parts listed in `docs/implementation/demo_acceptance.md` |
| Smoke from a clean checkout; replay with no network | PASS (clean-copy rehearsal; a literal `git clone` needs the work committed) |
| Backup and restore across DB, objects, runs, hashes verified | PASS (smoke steps backup/restore, replay from the restored copy) |
| Final walkthrough with a real-provider run and intentional failures | **BLOCKED**: owner not present, no live approval. Offline equivalents pass: source failure A04, relay refusing a bad token (`test_model_relay.py`), egress A27 |
| All G0–G7 outcomes recorded; plan 15.1 ticked or open | Recorded in `docs/implementation/demo_acceptance.md` (one item open: the live challenger campaign) |
| Final `DIAGNOSTICS.md` and `diagnose.jsonl` trend in the handoff | PASS: 40 full diagnose runs from 324 tests (2026-10-10) to 731 (2026-10-13); 2 regression flags and 3 FAIL verdicts in the trend, each explained in its journal |

