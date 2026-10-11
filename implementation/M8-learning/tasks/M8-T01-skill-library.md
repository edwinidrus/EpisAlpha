# M8-T01 — Skill library and ledger

| Field | Value |
|---|---|
| Status | TODO |
| Depends on | G7 |
| Phase constitution | [../CONSTITUTION.md](../CONSTITUTION.md) (inherits [global](../../CONSTITUTION.md), section VIII) |
| Plan source | amendment A13 |
| Journal | `tasks/M8-T01-skill-library.journal.md` |

## 0. Context to load

Load these and nothing else:
- `implementation/CONSTITUTION.md`, section VIII
- `implementation/M8-learning/CONSTITUTION.md`, articles 6–9 and 11
- [../PLAN.md](../PLAN.md)
- `src/episalpha/evolution/candidates.py` (M6-T02), the ledger and lineage pattern to reuse
- `src/episalpha/research/artifacts.py` (M4-T01), how `propose_skill` proposals and the
  skill-set hash are stored per run
- `src/episalpha/contracts/knowledge.py`, the `Contract` base, `Identifier` and `UtcTimestamp`
  conventions

## 1. Plan

- **Goal:** a versioned, append-only skill library with a ledger and a deterministic skill-set
  hash. It is the single source of truth for which skills exist, where each came from, and
  what state it is in.
- **Files:**
  - `src/episalpha/learning/skills.py` (new)
  - Focused test: `tests/learning/test_skills.py`
- **Produces:**
  - `SkillStatus(StrEnum)`, one of `proposed`, `quarantined`, `evaluating`, `rejected`,
    `promoted`, `revoked`.
  - `SkillProvenance(Contract)`, with `run_ids`, `stages`, `trajectory_hashes` and
    `evidence_span_ids`.
  - `SkillRecord(Contract)`, with `skill_id`, `version`, `content_hash`, `title`,
    `when_to_use`, `procedure_steps`, `provenance`, `status`, `created_at`, `promoted_at`,
    `approved_by`, `revoked_at`, `revoked_reason`.
  - `SkillLedger(path)`, an append-only JSON-lines log of state transitions, with these
    methods:
    - `append(record, transition, actor)`;
    - `history(skill_id)`;
    - `current()`, the latest state per skill.

    Transitions are validated against an allowed-transition table, so a skill cannot go from
    `rejected` straight to `promoted`.
  - `library_dir / "<skill_id>@v<n>/SKILL.md"`, written once and immutable. A rewrite is a new
    version.
  - `skill_set(as_of: datetime | None) -> tuple[SkillRecord, ...]`, the skills promoted, not
    revoked, and with `promoted_at <= as_of` when `as_of` is given.
  - `skill_set_hash(records) -> str`, the SHA-256 over sorted `(skill_id, version,
    content_hash)`. The empty set has a fixed, documented hash, the one v0.1 runs already
    record.
- **Out of scope:** screening (M8-T02), evaluation (M8-T03), the approval CLI and revocation
  cascade (M8-T04).
- **Do not:**
  - Delete or overwrite a library file or a ledger line.
  - Use a new SQLite table without an owner-approved migration. The JSON-lines ledger follows
    the M6-T02 pattern.

## 2. Verify (before building)

- [ ] Check the M6-T02 ledger pattern and the M4-T01 proposal artifacts exist as their journals
      describe. Check the v0.1 empty-set hash value recorded on runs.
- [ ] Baseline: the four checks and `diagnose.py` are green.
- [ ] **Red first.** Write `tests/learning/test_skills.py`. Cover:
  - The transition table: an illegal jump raises.
  - Append-only: the earlier lines are byte-identical after appends.
  - Version immutability: writing an existing `@vN` raises.
  - `skill_set(as_of)` excludes later promotions and revoked skills.
  - The hash is order-independent and stable, and the empty-set hash equals the recorded v0.1
    value.

## 3. Build

1. Write the contracts and the transition table.
2. Write the ledger: append, history, current.
3. Write the library writer, with atomic write and exclusive create.
4. Write `skill_set` and `skill_set_hash`.

## 4. Test

```bash
uv run pytest -q tests/learning/test_skills.py
uv run ruff check . && uv run ruff format --check . && uv run mypy src/episalpha && uv run pytest -q -m "not live"
```

Acceptance:
- [ ] Illegal transitions fail.
- [ ] The ledger is append-only.
- [ ] Versions are immutable.
- [ ] `skill_set` respects promotion time and revocation.
- [ ] The hash matches v0.1's empty-set value.

## 5. Diagnose

- [ ] `diagnose.py`: no regression; `tests/learning` appears.
- [ ] Journal: one sample ledger history for a synthetic skill (proposed → evaluating →
      rejected).

## 6. Stop and hand off

- **BLOCKED if:** M4-T01 did not persist proposals with provenance. Route the fix to M4-T01.
- **Record:** M8 `PROGRESS.md`, `STATUS.md`, and the journal.
- **Next:** M8-T02.
