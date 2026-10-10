# Gate G1: canonical contracts and invariants

**Status:** PASSED (2026-09-20) · **reopened** by A8 (M1-T05).

## Commands

```bash
uv run pytest -q tests/contracts tests/evidence/test_temporal.py tests/research/test_validation.py tests/research/test_derivations.py
# plus the four standard checks, and uv run python scripts/diagnose.py (from M0-T05)
```

## Criteria

- [x] Contracts reject naive timestamps, unknown statuses, malformed IDs, missing provenance,
      bad span ranges and context-less numeric facts.
- [x] The temporal fixture holds: version A at T1, corrected version B at T3, and a query at T2
      returns A.
- [x] The validator fails missing or mismatched citations, invalid relations and unsupported
      relabeling. Semantic status stays `unreviewed` without an assessment.
- [x] Schema version frozen at `1`.
- [ ] **A8:** every derived numeric claim is recomputed. A mismatch, an unknown method or
      incompatible inputs fails (M1-T05).
- [ ] The owner reviews representative serialized examples, including one derived claim.

## Results log (append-only; real output only)

### 2026-09-20 — PASSED

```
uv run pytest -q tests/contracts tests/evidence/test_temporal.py tests/research/test_validation.py
  -> 174 passed
uv run ruff check .            -> All checks passed
uv run ruff format --check .   -> 21 files already formatted
uv run mypy src/episalpha      -> Success: no issues found in 11 source files
uv run pytest -q -m "not live" -> 176 passed, 2 deselected
```

Re-run after the source-model expansion (M0-T02b): `uv run pytest -q -m "not live"` -> 185 passed,
2 deselected. All four standard checks still passed.

**Schema version frozen at `1`** (`episalpha.contracts.knowledge.SCHEMA_VERSION`).
