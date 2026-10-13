# Gate G6: research-quality experiment

**Status:** PARTIAL (2026-10-13): offline machinery passes on the fake runtime; the real-provider campaign is BLOCKED on owner decisions.

## Commands

```bash
uv run pytest -q tests/evaluation tests/evolution
uv run episalpha experiment compare --campaign demo-v1 --runtime fake
uv run python scripts/diagnose.py
# plus the four standard checks, and one real-provider campaign
```

## Criteria

- [ ] Metrics have correct direction and denominators. Omission cannot win (A17). `N/A` is
      handled.
- [ ] Only the allowed patch passes. Forbidden edits are rejected and recorded (A16).
- [ ] Labels cannot be loaded from research or tool paths. A hash change blocks comparison
      (A24).
- [ ] Fake and real execution IDs are distinct, and fake results never satisfy live.
- [ ] **One real-provider campaign completed.** The free-tier schedule or credit decision is
      recorded.
- [ ] Stored: the manifest, label and evaluator hashes, all trial IDs (failed ones included),
      the actual comparison report, and the owner decision.
- [ ] An honest rejection is accepted as a valid result (A18). No invented improvement.
- [ ] The `eval.trial` and `eval.decision` spans, linked to their run traces, reconstruct the
      campaign. No label content appears in Phoenix.

## Results log (append-only; real output only)

### 2026-10-13 — offline part (claude-opus-5-5)

- `uv run pytest -q tests/evaluation tests/evolution` -> `58 passed`.
- `uv run episalpha experiment compare --campaign demo-v1 --runtime fake` (scratch data root;
  the four development label drafts in a scratch sealed dir) -> `camp-880570ebbcb2b6c1`,
  `status: decided`, `decision: baseline_retained` (gate 0: no validation cases exist; gate 3:
  no new contradiction), exit 0. Re-run resumes with zero new trials and writes `report.md`.
- `--runtime hermes` -> `BLOCKED: no owner decision on free-tier capacity`, exit 2.
- `diagnose.py` -> `PASS | tests {'passed': 699, ...} | failures 0 | regressions 0 | orphans 0`.

| Criterion | Result |
|---|---|
| Metric direction, denominators, N/A, omission cannot win | PASS (`test_scoring.py`, 22; two mutation checks) |
| Only the allowed patch passes; rejections recorded | PASS (`test_candidates.py`, 16) |
| Labels refused to non-evaluators and inside the workspace; hash change = new campaign | PASS (tests; campaign ID hashes evaluator + label hashes) |
| Fake and real execution IDs distinct | PASS (`test_fake_and_live_campaigns_never_share_an_id`) |
| **One real-provider campaign** | **BLOCKED**: no capacity decision (`limits.campaign_requests_per_day`), labels not human-validated, 6 validation + 6 final cases do not exist |
| Stored manifest, hashes, trial IDs, report, owner decision | PARTIAL: all stored for the fake campaign; owner decision pending |
| Honest rejection is a valid result | PASS (fake campaign: `baseline_retained`, reported as complete) |
| `eval.trial` / `eval.decision` spans, no label content | PASS for the fake campaign (`spans.jsonl` scan: no label IDs); Phoenix not checked this session |

