# M4-T04 — Real thesis quality review

| Field | Value |
|---|---|
| Status | BLOCKED |
| Depends on | M4-T03, and the G2 owner checkpoint (live ingestion of LULU, TSCO and CALX) |
| Phase constitution | [../CONSTITUTION.md](../CONSTITUTION.md) (inherits [global](../../CONSTITUTION.md)) |
| Plan source | plan §10 M4-T04 card; A8; acceptance rows A01–A04 and A07 |
| Journal | `tasks/M4-T04-quality-review.journal.md` |
| Live calls | Yes. 3 cases, 24 requests or fewer on the free tier. Owner approval required. |

## 0. Context to load

Load these and nothing else:
- `implementation/CONSTITUTION.md`
- `implementation/M4-research-cli/CONSTITUTION.md`, article 10
- `eval_cases/manifests/lulu-guidance-2026q2.json`, `tsco-…` and `calx-…`
- The G2 owner-checkpoint record in `../../M2-evidence/GATE.md`
- The CLI from M4-T02/M4-T03

## 1. Plan

- **Goal:** run the three curated cases on the real route, then have a human inspect every
  material assertion, citation, numeric claim, counter-case and missing-expectation statement.
  Record what is true, including failures.
- **Files:**
  - `docs/implementation/demo_acceptance.md`, which holds the review record.
  - Narrow fixes go **only** to the responsible module, and **only after** the failed criterion
    is recorded.
- **Review checklist, per case and per assertion:**
  - [ ] Every cited span ID exists, and the quote matches the source passage.
  - [ ] Every number traces to a reported span or a recomputed derivation (A8). Recompute one
        by hand.
  - [ ] Unsupported claims are corrected, rejected or visibly `unreviewed`, never "verified".
  - [ ] The counter-case is present, and contradictions are not silently dropped.
  - [ ] Price and consensus unknowns are explicit. The unadjusted-price label is present where
        prices appear (A6).
  - [ ] Abstention fits the insufficient-evidence case.
  - [ ] `SOURCE_FAILED` is distinguishable from no evidence.
  - [ ] Historical mode shows the retrospective notice.
- **Evidence to store, per run:**
  - actual run ID;
  - model ID and `served_by`;
  - harness hash and snapshot hash;
  - duration;
  - requests and tokens (unknowns stay unknown);
  - review notes.

  No fabricated example metrics.
- **Do not:**
  - Weaken a validator.
  - Edit labels or annotations.
  - Re-run until something looks good. One run per case, plus one re-run per case only if a
    recorded fix requires it.

## 2. Verify (before building)

- [ ] The G2 owner checkpoint is done: the case mapping is confirmed, not PROVISIONAL. **If
      not, BLOCKED.**
- [ ] G3's live portion passed on the active route.
- [ ] Owner approval for the live runs is recorded, along with the free-tier requests remaining
      today.
- [ ] The four checks and `diagnose.py` are green.

## 3. Build

1. Run `uv run episalpha research run --case <case> --runtime hermes` for each case. Record the
   raw CLI output.
2. Review each thesis against the checklist. Write `demo_acceptance.md`, one section per case.
3. For each failed criterion: first record it (case, assertion, criterion, evidence). Then make
   a narrow fix in the responsible module, with its own test, and journal the attribution.

## 4. Test

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy src/episalpha && uv run pytest -q -m "not live"
```

Acceptance:
- [ ] No invented evidence IDs.
- [ ] Unsupported claims are corrected, rejected or visibly unreviewed.
- [ ] Essential missing evidence produces abstention.
- [ ] Source failure stays distinguishable from no evidence.
- [ ] Price and consensus unknowns are explicit.
- [ ] Every number traces to a span or a recomputed derivation.

## 5. Diagnose

- [ ] For each run, the `jq`-filtered event trail is saved next to the review, as the evidence
      of what happened.
- [ ] `diagnose.py`: no regression after any fix.
- [ ] Run G4 and append the result to `../GATE.md`.

## 6. Stop and hand off

- **BLOCKED if:**
  - the owner checkpoint is open;
  - the live route is down;
  - the daily cap is exhausted. Record the reset time and resume the next day.
- **Record:** M4 `PROGRESS.md`, `STATUS.md`, the journal, and `demo_acceptance.md`.
- **Next:** M5-T01.
