# M6-T04 journal — Experiment report and browser comparison

## Attempt 1 — 2026-10-13 — claude-opus-5-5
- Verify: the M6-T03 fake campaign ledger and decision exist (`camp-880570ebbcb2b6c1`, scratch
  data root). No live campaign (BLOCKED in M6-T03). Baseline green (690).
- Red first: `uv run pytest -q tests/evaluation/test_reporting.py` -> `ModuleNotFoundError:
  episalpha.evaluation.reporting`. Then two of my own test bugs (a `name` keyword clash; a
  loose `or` assertion, tightened before the first green run).
- Did:
  - `src/episalpha/evaluation/reporting.py` (new): `build_report` from `manifest.json` +
    `ledger.jsonl` only; `TrialRow` per trial (scored and interrupted), `Aggregate` per phase and
    variant (n/d sums, interrupted count, requests, tokens and cost `unknown`, latencies),
    gates in recorded order, candidate diff and harness hashes, final-check exposure, reuse
    warnings when an earlier campaign already ran the same final-check case; `render_markdown`
    starts with the fixed disclaimer; a rejection reads "a complete, valid result"; a pass
    reads "promotion is an explicit owner action". No score/total field (tested).
  - `apps/streamlit_app.py`: Experiments tab (campaign picker, disclaimer, FIXTURE label,
    decision badge, one bordered card per gate, every-trial and aggregate tables, candidate
    JSON, Markdown download). Logic stays in `reporting`.
  - `src/episalpha/cli.py`: `experiment compare` writes `<campaign>/report.md`.
  - `docs/implementation/demo_script.md`: step 7, the experiment segment.
  - Tests: `tests/evaluation/test_reporting.py` (8); one AppTest in `tests/ui/test_workbench.py`.
- Ran:
  - `uv run pytest -q tests/ui tests/evaluation` -> `55 passed`.
  - CLI re-run on the existing campaign resumed it with zero new trials and wrote `report.md`
    (disclaimer first; `labels NOT human-validated` shown).
  - Real Streamlit (127.0.0.1:8596) + headless Chromium: Experiments tab shows all of the
    above; screenshot checked.
  - Four checks green; `diagnose.py` -> `PASS | tests {'passed': 699, ...} | regressions 0 |
    orphans 0`.
- Noted, not changed: with zero validation cases gates 2 and 4 read PASS with detail "no
  cases" (vacuous); gate 0 fails, so the decision is right. Revisit if it confuses the owner.
- Outcome: DONE_OFFLINE. The live campaign report and the owner promotion decision do not exist
  (G6 live part BLOCKED).
