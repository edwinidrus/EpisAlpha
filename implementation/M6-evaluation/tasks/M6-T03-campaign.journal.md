# M6-T03 journal — Offline campaign runner

## Attempt 1 — 2026-10-12/13 — claude-opus-5-5
- Verify:
  - Owner capacity decision: **not recorded**. Labels: **not human-validated**. So the live
    campaign is BLOCKED; the fake path was built and completed (pack section 6).
  - Baseline green (678).
  - **Process deviation:** `campaign.py` was written before `test_campaign.py`, not red first.
    The tests then found two real defects (below), but the order is recorded as it happened.
- Found while building, fixed:
  1. `services.new_request` always stamped `harness.baseline`, and the Hermes runtime always
     loaded `harnesses/baseline`: a challenger run would silently have used the baseline harness.
     Now the request carries its `harness_id`; `Workbench.harness_root` maps `harness.baseline`
     to the repository and `harness.cand-<16 hex>` to a materialized candidate; the runtime and
     the runner load that harness.
  2. The runner's new contradiction step first kept only passages sharing words with the claim;
     the synthetic counter-passage shares none (`test_the_runner_adds_...` failed with no hits).
     Overlap now only orders candidates.
  3. The decision-rule test helper lacked metrics (`KeyError`); test fixed.
- Did:
  - `src/episalpha/evolution/campaign.py` (new): manifest frozen first (rule, partitions,
    evaluator and label hashes, labels_reviewed, budgets, runtime, model, baseline harness hash;
    the campaign ID hashes it), development baseline, author inputs (failure summary + patch
    schema only), proposal via `candidates.propose`/`materialize`, paired validation (challenger
    on the baseline run's own snapshot), gates 0–4, final check only after all pass (gate 5),
    decision with no automatic replacement. Trials recorded scored or interrupted; scored trials
    never re-run; interrupted ones resume as attempt n+1; daily cap -> `paused`, resumable.
    Spans `eval.trial` (IDs, state, metric n/d; no label content) and `eval.decision`.
  - `src/episalpha/research/runner.py`: optional `harness_config`; when `contradiction_search`
    is true, one host retrieval per validated claim (at most `limits.max_contradiction_queries`)
    over the frozen snapshot's spans the claim does not cite, at most `max_evidence_search_hits`
    each, appended to the critic brief, saved as artifact `contradiction_search`, span
    `tool.contradiction_search` (RETRIEVER).
  - `src/episalpha/research/services.py`: harness selection above; `candidates_dir`.
  - `src/episalpha/settings.py`: `limits.max_contradiction_queries` (3),
    `limits.campaign_requests_per_day` (None = no owner decision: live refused).
  - `src/episalpha/cli.py`: `experiment compare --campaign NAME --runtime fake|hermes`
    (exit 0 decided, 5 paused, 2 refused).
  - `eval_cases/campaigns/demo-v1/proposal.json` (the scripted one-flag proposal).
  - `tests/evolution/test_campaign.py` (12).
- Scope note: 5 implementation files instead of 1–3 (campaign, runner, cli as the pack lists,
  plus services for the harness defect and settings for the two limits, article 21).
- Ran:
  - `uv run pytest -q tests/evolution` -> `28 passed`.
  - `uv run episalpha experiment compare --campaign demo-v1 --runtime fake` (scratch data root,
    the four development drafts copied into a scratch sealed dir) -> `camp-880570ebbcb2b6c1`,
    `decided`, gate 0 FAIL (0 validation cases: none exist yet), gate 3 FAIL, `decision:
    baseline_retained`, exit 0.
  - Same with `--runtime hermes` -> `BLOCKED: no owner decision on free-tier capacity`, exit 2.
  - Spans (Python over `spans.jsonl`, no jq installed): 4 × `eval.trial` (development
    baseline: demand-vs-revenue contradiction 1/1, order-book completion 0/1 because the fake
    run answered where the label says abstain, two extraction cases 1/1), `candidate.review`,
    `eval.decision baseline_retained`. No label ID or value in any span.
  - Four checks green; `diagnose.py` -> `PASS | tests {'passed': 690, ...} | regressions 0 |
    orphans 0`.
- Free-tier requests spent: 0 (no live call made).
- Outcome: DONE_OFFLINE. Live campaign BLOCKED: capacity decision, label review, and the 6
  validation + 6 final cases do not exist yet.
