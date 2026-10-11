# M4-T04 journal

## Attempt 1 — 2026-10-11 07:10 UTC — claude-opus-5-5 — BLOCKED
- Verify (pack section 2):
  - **G2 owner checkpoint: NOT done.** `eval_cases/manifests/*.json` still say `"status":
    "PROVISIONAL"`; the live ingestion and hand inspection of LULU, TSCO and CALX have not
    happened (`implementation/M2-evidence/GATE.md`). The pack says: "If not, BLOCKED."
  - G3 live portion: passed (2026-10-11).
  - Live approval: the unattended-session approval (up to 40 requests) is not an approval of
    these specific runs, and the remaining budget (about 12) would not cover three cases at up
    to 8 requests each anyway.
- Decision: BLOCKED. No real-case run was started, so none of the "one run per case" allowance
  is spent.
- What is ready for when the owner unblocks it:
  - `uv run episalpha research run --case <supported|conflicting|insufficient> --runtime hermes`
    works end to end. Without ingested filings it abstains at freeze with zero model calls
    (tested), so the missing step is ingestion plus the owner's inspection.
  - Each run's trace ID, artifacts, replay (`episalpha replay RUN_ID`) and usage are recorded
    automatically, which is what `docs/implementation/demo_acceptance.md` needs.
- Owner actions to unblock:
  1. Live ingestion of the three cases' filings, and hand inspection of their key quotations
     (G2 checkpoint); then mark each manifest `CONFIRMED` or reassign its case.
  2. Approve the real runs (about 24 free-tier requests at most).
- Diagnose: n/a (no code change).
