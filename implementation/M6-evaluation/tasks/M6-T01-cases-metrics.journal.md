# M6-T01 journal — Labeled cases and deterministic metrics

## Attempt 1 — 2026-10-12 21:00 UTC — claude-opus-5-5
- Context: started on the owner's 2026-10-12 "full auto" message, past G5 PARTIAL (recorded in
  `docs/implementation/progress.md`, owner inputs). No live calls, no commits.
- Verify:
  - Pre-repair numbers are recorded: the runner writes `stages/<stage>-<attempt>` with the raw
    candidate payload for every attempt (`runner.py` `_attempt`); a repair is attempt 2 of the
    same stage. Not BLOCKED.
  - Baseline four checks and `diagnose.py` green (640 passed before this task).
  - Red first: `uv run pytest -q tests/evaluation/test_scoring.py` -> collection error,
    `episalpha.evaluation` missing (expected reason).
- Decisions:
  - **Sealed labels:** `evaluation.labels_dir` (new setting, absolute). `load_labels` refuses
    any caller but `evaluator` (`NOT_AUTHORIZED`) and any directory inside `project_root` or
    `data_root`. That is the whole agent-accessible workspace: the worker sees only a snapshot
    and a stage directory under `data_root`; a candidate author can read the repository.
  - **Numeric correctness (A8):** derived numbers in each stage's first attempt (claims and
    critic counter-claims) that recompute through the registry at their stated precision ÷
    derived numbers proposed. Inputs resolve from the same proposals (`<run>.<key>`) or
    persisted claims; an unresolvable input counts as proposed and wrong. Reported numbers are
    checked by citation correctness instead; recomputation cannot judge them. `N/A` when none.
  - **Answer = persisted records:** a REJECTED run answered nothing.
  - **Completion / correct abstention:** the label says which output is required
    (`should_abstain` true -> ABSTAINED, false -> RESEARCH_COMPLETED, unset -> either). A
    provider failure is never a correct abstention. Abstention has a denominator only when the
    label asks for a decision.
  - **Precision-type metrics** count what was emitted, so an empty answer is `N/A` there, never
    1; it loses recall, completion and abstention instead.
  - **Violations:** temporal = snapshot documents not eligible at the cutoff (rechecked with
    `evidence.temporal.is_eligible`; the validator has no temporal check); boundary = cited
    spans outside the manifest; reference = failed validation checks.
  - **Dataset:** I cannot author human-reviewed gold labels, and the only evidence available
    offline is one synthetic document. So: 4 development cases (`eval_cases/campaigns/demo-v1/
    cases/`), label **drafts** in `docs/implementation/m6-label-drafts/development/`
    (`reviewed_by: null`; dev labels are visible by design), and a README listing what the
    owner must add (8 more dev, 6 validation, 6 final; four uncovered case types). No
    validation/final labels were written: a draft in the repository would leak them.
- Did: `src/episalpha/evaluation/{__init__,cases,scoring}.py` (new), `settings.py`
  (`EvaluationConfig`), case files, drafts, README, `tests/evaluation/test_scoring.py` (22).
- Ran:
  - `uv run pytest -q tests/evaluation` -> `22 passed`.
  - Mutation checks: dropping the first-attempt filter -> `1 failed`; making an abstention
    label accept a completed answer -> survived at first (`21 passed`), so I added
    `test_answering_when_the_honest_answer_is_to_abstain_is_wrong` -> mutation now `1 failed`.
    Code restored, `22 passed`.
  - Four checks: ruff clean, `88 files already formatted`, mypy `no issues found in 41 source
    files`; `diagnose.py` -> `PASS | tests {'passed': 662, ...} | failures 0 | regressions 0 |
    orphans 0`.
- Hashes over the **drafts** (identities change when the owner signs and copies them):
  evaluator `09df80abe07d9ffa7709efb3fc2e1c1c372ec5516aa8ca11cb377994e389ac34`, labels
  `6cf3cb629f3a76e960f3448d783e3e5c5b9ad657623a40c84e30523f57a619a2`.
- Outcome: DONE_OFFLINE. Blocked part: the owner label review and the missing 20 cases.
- Diagnose: PASS, 0 regressions; no spans in this task (`eval.trial` belongs to M6-T03).
