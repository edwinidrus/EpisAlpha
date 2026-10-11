# M1 progress

One row per task. A task is DONE only when its acceptance checks actually pass, with the real
command output recorded here. Keep `../STATUS.md` in step. Commits are an owner action.

Rows for completed tasks were migrated unchanged from `docs/implementation/progress.md` on
2026-10-10 (amendment A10).

| Task | Status | Changes | Verification | Blocker | Next |
|---|---|---|---|---|---|
| M1-T01 | DONE | `src/episalpha/contracts/knowledge.py`, `tests/fixtures/synthetic_knowledge.py`, `tests/contracts/test_knowledge.py`, `tests/conftest.py` — Entity, Instrument, EvidenceDocument, EvidenceSpan, Claim, NumericFact, Derivation, Event, Hypothesis, Relation, SemanticAssessment; frozen vocabularies; `ALLOWED_ENDPOINTS` from plan section 3.4. | 2026-09-20: `uv run pytest -q tests/contracts/test_knowledge.py` → 44 passed | None | M1-T02 |
| M1-T02 | DONE | `src/episalpha/contracts/research.py`, `src/episalpha/contracts/errors.py`, `tests/contracts/test_research.py` — RunRequest, SnapshotManifest, ThesisAssertion, Thesis, RunRecord, ValidationReport, RuntimeContext, StageResult, Usage, Budgets; transition validator; eight frozen error codes. | 2026-09-20: `uv run pytest -q tests/contracts/test_research.py` → 60 passed | None | M1-T03 |
| M1-T03 | DONE | `src/episalpha/evidence/temporal.py`, `tests/evidence/test_temporal.py` — pure eligibility functions implementing plan section 3.5 rules 1-9, including the version-A/version-B selection fixture. | 2026-09-20: `uv run pytest -q tests/evidence/test_temporal.py` → 19 passed | None | M1-T04 |
| M1-T04 | DONE | `src/episalpha/research/validation.py`, `tests/research/test_validation.py` — reference resolution, relation endpoint/kind checks, exact quotation verification, derivation checks, assertion coverage, semantic-status enforcement. | 2026-09-20: `uv run pytest -q tests/research/test_validation.py` → 20 passed | None | M2-T01 |
| M1-T05 | DONE | `src/episalpha/research/derivations.py` (new: `REGISTRY` of six pure-Decimal methods at version 1, `recompute`, `matches` half-even at the claimed precision, `DerivationError`), `src/episalpha/research/validation.py` (`check_derivations` after `check_claim_references`), `tests/research/test_derivations.py` (29 tests). Schema unchanged. | 2026-10-10: `uv run pytest -q tests/research` → 49 passed; G1 command set → 212 passed; four checks green, `pytest -m "not live"` → 370 passed, 3 deselected; `git diff src/episalpha/contracts` empty | None | M2-T05 |
