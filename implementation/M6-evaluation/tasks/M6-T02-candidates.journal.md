# M6-T02 journal — Candidate validation and lineage

## Attempt 1 — 2026-10-12 21:30 UTC — claude-opus-5-5
- Verify: `harnesses/baseline/config.json` is `{"schema_version": "1", "contradiction_search":
  false}` (asserted by a test). Baseline green (662). Red first: `uv run pytest -q
  tests/evolution` -> `ModuleNotFoundError: No module named 'episalpha.evolution'`.
- Did:
  - `src/episalpha/evolution/candidates.py` (new): `CandidateProposal` (closed schema, so an
    extra field such as `code` is refused), `validate_proposal` (parent must be the baseline's
    harness ID; exactly one op; `replace`; path `/contradiction_search`; a real boolean, not
    `1`; different from the parent), `propose` (records accepted or rejected, then re-raises),
    `materialize` (copy to `<candidates>/.<id>.tmp`, patch, rename; refuses a target inside the
    baseline; refuses a baseline that changed since validation; reuses an existing directory
    only when it equals baseline plus patch), `abandon`, `Ledger` (append-only JSON lines).
    The `candidate.review` span (EVALUATOR) wraps each review.
  - `src/episalpha/evolution/__init__.py`; 9 proposal fixtures in `tests/fixtures/candidates/`.
  - `tests/evolution/test_candidates.py` (16).
- Decisions: parent and child hashes reuse `runtime.hermes.load_harness` (stdlib-only module),
  so a candidate's hash is exactly the hash a run records for it. Candidate ID =
  `cand-` + 16 hex of SHA-256 over parent hash and proposal: the same proposal on the same parent
  is the same candidate. Lineage lives in the ledger, not in the candidate directory (a file
  there would change the child's harness hash).
- Ran: `uv run pytest -q tests/evolution` -> `16 passed`; four checks green; `diagnose.py` ->
  `PASS | tests {'passed': 678, ...} | regressions 0 | orphans 0`; `git status harnesses` clean.
- Ledger samples (scratch directory; `proposal` field omitted here for length):
  ```
  {"campaign_id": "sample", "candidate_id": "cand-d40d63c1e69e446c", "kind": "proposal_accepted", "parent_harness_hash": "de8654323245a7132ae0401643b77c19747eb06b209547e252df0ea467a45610", "parent_harness_id": "harness.baseline", ...}
  {"campaign_id": "sample", "candidate_id": "cand-d40d63c1e69e446c", "child_harness_hash": "f41ae727279a8c8c9f6cab281dd6c6efee7645048c2f5adbae8d362bfa34f4a5", "kind": "materialized", ...}
  {"campaign_id": "sample", "kind": "proposal_rejected", "reason": "INVALID_OUTPUT: only /contradiction_search may change, not '/budgets'", ...}
  ```
- Outcome: PASS.
- Diagnose: PASS, 0 regressions; span `candidate.review` emitted per proposal.
