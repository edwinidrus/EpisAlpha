# M6-T02 — Candidate validation and lineage

| Field | Value |
|---|---|
| Status | TODO |
| Depends on | M6-T01 |
| Phase constitution | [../CONSTITUTION.md](../CONSTITUTION.md) (inherits [global](../../CONSTITUTION.md)) |
| Plan source | plan §12.2 candidate surface, M6-T02 card; acceptance row A16 |
| Journal | `tasks/M6-T02-candidates.journal.md` |

## 0. Context to load

Load these and nothing else:
- `implementation/CONSTITUTION.md`
- `implementation/M6-evaluation/CONSTITUTION.md`, articles 3, 4 and 7
- `harnesses/baseline/config.json` (M3-T03)

The only permitted patch:

```json
{
  "parent_harness_id": "<existing baseline id>",
  "hypothesis": "An explicit contradiction retrieval step improves recall without adding unsupported claims.",
  "patch": [
    {"op": "replace", "path": "/contradiction_search", "value": true}
  ]
}
```

## 1. Plan

- **Goal:** a strict validator for a single operation, plus an append-only candidate ledger.
  The baseline is never modified in place.
- **Files:**
  - `src/episalpha/evolution/candidates.py`
  - Candidate fixtures under `tests/fixtures/candidates/`
  - Focused test: `tests/evolution/test_candidates.py`
- **Produces:**
  - `CandidateProposal(Contract)`, with `parent_harness_id`, `hypothesis`, `rationale` and
    `patch`.
  - `validate_proposal(p, baseline_config) -> ValidatedCandidate`. It raises a typed error
    unless the patch is exactly one `replace` on `/contradiction_search` with a boolean value
    that differs from the parent.
  - `materialize(candidate) -> Path`. It writes a new candidate directory under
    `.episalpha/candidates/<candidate_id>/`, copying the baseline harness and applying the
    patch. It records the parent and child hashes.
  - `Ledger`, an append-only campaign and trial record. Rejected and abandoned proposals are
    kept.
- **Do not:**
  - Implement general JSON-Patch. Only this one operation is allowed.
  - Write to `harnesses/baseline/`.
  - Execute anything from a proposal.

## 2. Verify (before building)

- [ ] `harnesses/baseline/config.json` matches `{"schema_version": "1", "contradiction_search": false}`.
- [ ] Baseline: the four checks and `diagnose.py` are green.
- [ ] **Red first.** Write `test_candidates.py`. Cover:
  - The allowed flag change passes.
  - Each of these fails and is recorded in the ledger:
    - an empty patch;
    - a duplicate operation;
    - multiple operations;
    - a path other than `/contradiction_search`, such as `/budgets` or `../file`;
    - a non-boolean value;
    - an unchanged value.
  - The baseline directory hash is unchanged after `materialize`.

## 3. Build

1. Write the proposal schema and the strict validator.
2. Write `materialize`, with hash lineage.
3. Write the ledger, stored as JSON lines under `.episalpha/candidates/ledger.jsonl` with an
   `eval.trial`-style event.

## 4. Test

```bash
uv run pytest -q tests/evolution/test_candidates.py
uv run ruff check . && uv run ruff format --check . && uv run mypy src/episalpha && uv run pytest -q -m "not live"
```

Acceptance:
- [ ] Only the allowed flag change passes.
- [ ] Empty, duplicate, multiple, arbitrary-file or budget-changing patches fail.
- [ ] Failed and abandoned proposals are retained in the ledger.
- [ ] The active harness remains unchanged.

## 5. Diagnose

- [ ] `diagnose.py`: no regression.
- [ ] Ledger samples (one accepted, one rejected) are in the journal.

## 6. Stop and hand off

- **Record:** M6 `PROGRESS.md`, `STATUS.md`, and the journal.
- **Next:** M6-T03.
