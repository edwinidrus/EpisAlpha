# M7-T03 — Final owner walkthrough

| Field | Value |
|---|---|
| Status | TODO |
| Depends on | M7-T02 |
| Phase constitution | [../CONSTITUTION.md](../CONSTITUTION.md) (inherits [global](../../CONSTITUTION.md)) |
| Plan source | plan §13 M7-T03 card, §15 definition of done |
| Journal | `tasks/M7-T03-walkthrough.journal.md` |
| Live calls | Yes. One real run plus one intentional model failure. Owner present. |

## 0. Context to load

Load these and nothing else:
- `implementation/CONSTITUTION.md`
- `implementation/M7-acceptance/CONSTITUTION.md`
- `docs/implementation/demo_script.md` and `demo_acceptance.md`
- every phase `GATE.md` (G0–G7 results)
- `implementation/DIAGNOSTICS.md` and `implementation/logs/diagnose.jsonl`

## 1. Plan

- **Goal:** the owner sees the full demo live. Every gate outcome and every limitation is
  recorded truthfully, and the next eligible work is named but not started.
- **Files:**
  - `docs/implementation/demo_script.md`
  - `docs/implementation/demo_acceptance.md`
  - `docs/implementation/progress.md` (the final handoff section)
- **Perform:**
  1. A real-provider research run on the active route.
  2. Saved replay.
  3. Source inspection.
  4. Contradiction and unknowns.
  5. The local graph.
  6. Obsidian export.
  7. The measured candidate comparison, from the M6 live campaign.
  8. An intentional source failure (for example, a blocked host) and an intentional model
     failure (for example, an invalid token at the relay). Both must show honest states.
- **Record:**
  - the actual machine, OS and WSL version;
  - versions: Python, Hermes pin, Streamlit, and the model ID with `served_by`;
  - run IDs;
  - latency and usage;
  - limitations;
  - all G0–G7 outcomes.
- **Handoff:** the next eligible work is forward forecast logging, then the optional
  paper/evaluation lab, then the A8 follow-ons in plan §15.3 (event-window reaction, factor
  baselines, Deflated Sharpe and PBO). **Do not start them.**

## 2. Verify (before building)

- [ ] G0–G6 results are recorded. G7 automated checks pass (`demo_smoke.py`, the four checks).
- [ ] The owner is present, has approved the live calls, and the free-tier requests remain for
      today.

## 3. Build

1. Run the walkthrough, step by step, timing each step. Record the evidence in
   `demo_acceptance.md`.
2. Tick the definition-of-done checklist (plan §15.1) with evidence links. Mark anything open
   explicitly.
3. Write the handoff section in `progress.md`.

## 4. Test

```bash
uv run python scripts/demo_smoke.py
set -a; . ./.env; set +a
uv run pytest -q -m live tests/integration/test_hermes_runtime.py tests/integration/test_runtime_boundary.py
uv run ruff check . && uv run ruff format --check . && uv run mypy src/episalpha && uv run pytest -q -m "not live"
```

Acceptance:
- [ ] The actual machine, versions, run IDs, latency and usage, limitations, and all G0–G7
      outcomes are recorded.
- [ ] No required acceptance item remains silently incomplete.

## 5. Diagnose

- [ ] The final `diagnose.py` run is archived. The `diagnose.jsonl` trend is summarized: tests
      over time, regressions caught.
- [ ] The walkthrough run's event trail is archived with its run IDs.
- [ ] Run G7 and append the result to `../GATE.md`.

## 6. Stop and hand off

- **BLOCKED if:** the owner is not present, or the live route is unavailable. In that case,
  report the offline result separately.
- **Record:** M7 `PROGRESS.md`, `STATUS.md`, the journal, and `progress.md`.
- **Next:** none in v0.1. The follow-on work is named in the handoff.
