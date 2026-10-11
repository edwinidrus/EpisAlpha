# M8-T02 — Harvest and deterministic screening

| Field | Value |
|---|---|
| Status | TODO |
| Depends on | M8-T01 |
| Phase constitution | [../CONSTITUTION.md](../CONSTITUTION.md) (inherits [global](../../CONSTITUTION.md), section VIII) |
| Plan source | amendment A13; acceptance row A30 |
| Journal | `tasks/M8-T02-screening.journal.md` |

## 0. Context to load

Load these and nothing else:
- `implementation/CONSTITUTION.md`, sections VI and VIII
- `implementation/M8-learning/CONSTITUTION.md`, articles 2–4 and 11
- `implementation/M3-runtime/CONSTITUTION.md`, article 14 (the hostile-output reader rules)
- `src/episalpha/learning/skills.py` (M8-T01)
- `src/episalpha/research/artifacts.py`, the proposal artifacts
- `src/episalpha/runtime/tools.py`, the tool allowlist names
- `src/episalpha/settings.py`, `demo.companies` (the universe tickers to forbid)

## 1. Plan

- **Goal:** turn raw `propose_skill` proposals from completed runs into either *candidates* or
  *quarantined* records, using only deterministic, explainable rules.
- **Files:**
  - `src/episalpha/learning/screening.py` (new)
  - Focused test: `tests/learning/test_screening.py`
- **Produces:**
  - `harvest(run_ids) -> list[SkillRecord]`. It reads proposals through the article 14 reader
    and attaches provenance: run ID, stage, trajectory hash and span IDs. It writes `proposed`
    to the ledger.
  - `screen(record) -> ScreenResult`. The result holds `admitted: bool` and `findings: list[(rule_id, excerpt)]`.
    An admitted record becomes `evaluating`; a rejected one becomes `quarantined`.
  - **Rules (frozen list, versioned as `SCREEN_RULES_VERSION`):**

    | Rule ID | Rejects |
    |---|---|
    | `R1-size` | total over 4 KiB, more than 12 steps, or a step over 300 characters |
    | `R2-ticker` | any universe ticker or issuer name, case-insensitive with word boundaries |
    | `R3-dated-fact` | year-like tokens (`19xx`/`20xx`), quarter labels (`Q[1-4]`, `FY`) |
    | `R4-number-unit` | numbers with currency or percent units (`$`, `%`, `USD`, `bp`) |
    | `R5-url` | URLs, domains, IP addresses, file paths |
    | `R6-tool` | a backticked tool name not in the EpisAlpha allowlist (`terminal`, `browser`, `skill_manage`, …) |
    | `R7-injection` | phrases such as "ignore previous", "system prompt", "you are now", "exfiltrate", "send to", and base64 blobs |
    | `R8-unicode` | invisible or bidi control characters (U+200B–U+200F, U+202A–U+202E, U+2066–U+2069) |
    | `R9-evidence` | `evidence_span_ids` empty, or not in the run's snapshot |

  - `dedupe(records)`. Normalized-text near-duplicates of an existing promoted or evaluating
    skill are merged as provenance, never as a second candidate.
- **Out of scope:**
  - Any LLM-based judgement. An optional LLM review may only add warnings (constitution
    article 3), and is not part of this task.
  - Evaluation (M8-T03).
- **Do not:**
  - Execute or render proposal text.
  - Log skill text. Log its hash and the rule IDs.

## 2. Verify (before building)

- [ ] The proposal artifacts carry run ID, stage and span IDs, as the M4-T01 journal shows.
- [ ] Baseline: the four checks and `diagnose.py` are green.
- [ ] **Red first.** Write `test_screening.py` with fixtures. Cover:
  - A clean procedural skill, for example "When guidance changes, locate both ranges, call
    `compute_derivation` with `guidance_revision`, and cite both spans." It is admitted.
  - One fixture per rule, R1–R9, each quarantined with the right rule ID and excerpt.
  - A SkillJack-style fixture: a plausible procedure with an embedded trigger phrase. It is
    quarantined.
  - A symlinked proposal file is not followed.
  - A near-duplicate is merged.

## 3. Build

1. Write the harvest step, using the article 14 reader and provenance.
2. Write the rule functions, each pure and returning findings.
3. Write `screen` and the ledger transitions.
4. Write `dedupe`.

## 4. Test

```bash
uv run pytest -q tests/learning/test_screening.py
uv run ruff check . && uv run ruff format --check . && uv run mypy src/episalpha && uv run pytest -q -m "not live"
```

Acceptance:
- [ ] Every rule has a passing negative fixture.
- [ ] Clean procedural skills are admitted.
- [ ] Poisoned and factual proposals are quarantined, with the rule named (A30).
- [ ] No symlink is followed.

## 5. Diagnose

- [ ] `diagnose.py`: no regression.
- [ ] `skill.proposed` and `skill.screened` events are present, with rule IDs and no text.

## 6. Stop and hand off

- **Record:** M8 `PROGRESS.md`, `STATUS.md`, and the journal.
- **Next:** M8-T03.
