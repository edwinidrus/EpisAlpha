# M6-T04 — Experiment report and browser comparison

| Field | Value |
|---|---|
| Status | TODO |
| Depends on | M6-T03 |
| Phase constitution | [../CONSTITUTION.md](../CONSTITUTION.md) (inherits [global](../../CONSTITUTION.md)) |
| Plan source | plan §12.3, M6-T04 card; acceptance row A18 |
| Journal | `tasks/M6-T04-report.journal.md` |

## 0. Context to load

Load these and nothing else:
- `implementation/CONSTITUTION.md`
- `implementation/M6-evaluation/CONSTITUTION.md`, articles 1, 5–8
- `src/episalpha/evolution/campaign.py` (the ledger and decision output)
- `src/episalpha/evaluation/scoring.py`
- `apps/streamlit_app.py`, the Experiments tab placeholder
- `docs/implementation/demo_script.md`, which reserves the experiment segment

## 1. Plan

- **Goal:** an honest comparison report, in Markdown and in the browser Experiments tab. Each
  gate is shown separately, every trial is shown including failures, and the report is
  impossible to read as a financial-alpha claim.
- **Files:**
  - `src/episalpha/evaluation/reporting.py`
  - `apps/streamlit_app.py`
  - `docs/implementation/demo_script.md`
  - Focused test: `tests/evaluation/test_reporting.py`
- **Report contents:**
  - The candidate diff.
  - Per-case paired results.
  - Aggregates as numerator and denominator.
  - Failures and interrupted trials.
  - Usage and cost, with unknown shown as unknown.
  - Latency.
  - Each decision-rule gate shown pass/fail with evidence.
  - The final accept or reject decision, with reasons.
  - A fixed disclaimer: "Research-quality experiment on a small engineering sample; not
    evidence of investment performance or statistical generalization."
- **No hidden weighted score.** Decision order follows the manifest's frozen rule.
- **Do not:**
  - Use illustrative numbers. Only measured values from the ledger.
  - Use "improved" phrasing for a rejected candidate.

## 2. Verify (before building)

- [ ] The M6-T03 ledger and decision exist for a fake campaign, and for the live one if it was
      completed.
- [ ] Baseline: the four checks and `diagnose.py` are green.
- [ ] **Red first.** Write `test_reporting.py`. Cover:
  - A failed trial appears in the report.
  - A rejected candidate is shown as a complete, valid result.
  - The disclaimer is always present.
  - There is no aggregate score field.
  - Final-check cases are marked "exposed", and a reuse attempt is flagged.

## 3. Build

1. Write the report model and Markdown renderer.
2. Write the Experiments tab, which reads the report and shows per-gate cards.
3. Write the experiment segment of `demo_script.md`.

## 4. Test

```bash
uv run pytest -q tests/evaluation
uv run ruff check . && uv run ruff format --check . && uv run mypy src/episalpha && uv run pytest -q -m "not live"
```

Acceptance:
- [ ] The report cannot hide failed trials or imply financial alpha.
- [ ] Actual measured outcomes replace illustrative numbers.
- [ ] Candidate rejection is a complete valid result.
- [ ] Final-check cases are not reused for tuning after exposure.
- [ ] **Owner action:** any promotion is explicit, versioned and linked to the report. Choosing
      not to promote is acceptable.

## 5. Diagnose

- [ ] `diagnose.py`: no regression.
- [ ] Run G6 and append the result to `../GATE.md`, with the live campaign report path and the
      owner decision.

## 6. Stop and hand off

- **Record:** M6 `PROGRESS.md`, `STATUS.md`, and the journal.
- **Next:** M7-T01.
