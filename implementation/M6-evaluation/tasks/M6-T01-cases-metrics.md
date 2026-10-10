# M6-T01 — Labeled cases and deterministic metrics

| Field | Value |
|---|---|
| Status | TODO |
| Depends on | G5 |
| Phase constitution | [../CONSTITUTION.md](../CONSTITUTION.md) (inherits [global](../../CONSTITUTION.md)) |
| Plan source | plan §12.1, §12.3 metric table, M6-T01 card; A8 (numeric correctness) |
| Journal | `tasks/M6-T01-cases-metrics.journal.md` |

## 0. Context to load

Load these and nothing else:
- `implementation/CONSTITUTION.md`
- `implementation/M6-evaluation/CONSTITUTION.md`, articles 2, 6, 10 and 12
- [../PLAN.md](../PLAN.md), the dataset contract
- `eval_cases/README.md`, `eval_cases/manifests/*.json`, `eval_cases/development/*.json`
- `src/episalpha/research/artifacts.py` (how completed run artifacts are read)
- `src/episalpha/settings.py` (where an evaluator-only labels path setting would live)

**Metric definitions, case-level numerators and denominators, pooled over the same eligible
cases (plan §12.3):**

| Metric | Definition |
|---|---|
| Citation correctness | Emitted citation links that match the labelled supporting passage ÷ emitted citation links |
| Numeric correctness (A8) | Model-proposed numbers matching recomputation **before repair** ÷ model-proposed numbers |
| Supported-claim precision | Factual claims assessed supported ÷ emitted factual claims (hypotheses reported separately) |
| Required-fact recall | Distinct expected fact IDs recovered ÷ expected fact IDs |
| Contradiction recall | Distinct expected contradiction IDs recovered ÷ expected contradiction IDs |
| Correct abstention | Cases whose abstain decision matches the label ÷ cases requiring that decision |
| Completion | Completed required outputs ÷ attempted cases |

Also reported: temporal violations, model requests, available usage and cost, and latency.

## 1. Plan

- **Goal:** a versioned case schema, partition checks, sealed label loading, an evaluator hash,
  and per-case and pooled metrics that cannot be gamed by omission.
- **Files:**
  - `src/episalpha/evaluation/cases.py`
  - `src/episalpha/evaluation/scoring.py`
  - `eval_cases/manifests/` plus development fixtures
  - Focused test: `tests/evaluation/test_scoring.py`
- **Produces:**
  - `EvalCase(Contract)`, with `case_id`, `partition`, `family_id`, `case_type`, snapshot
    reference and question.
  - `Labels(Contract)`, with expected fact IDs, contradiction IDs, abstain flag and supporting
    span IDs.
  - `load_labels(path, *, caller)`. It refuses unless `caller` is the evaluator, and it refuses
    any path inside the agent-accessible workspace.
  - `evaluator_hash()`, the SHA-256 over the scoring source and the label files.
  - `score_case(artifacts, labels) -> CaseScore`.
  - `pool(scores) -> PooledScore`. Each metric carries its numerator and denominator, or
    `N/A`.
- **Do not:**
  - Put labels under `eval_cases/` if that is agent-mounted. Labels live at the evaluator-only
    path from settings.
  - Let an empty answer score precision 1.
  - Drop failed cases from denominators.

## 2. Verify (before building)

- [ ] The run artifacts expose citations, claims, numeric proposals before repair, and terminal
      state. **The M4-T01 runner must have recorded pre-repair candidate numbers. If it did not,
      BLOCKED,** with the fix routed to M4-T01.
- [ ] Baseline: the four checks and `diagnose.py` are green.
- [ ] **Red first.** Write `test_scoring.py`. Cover:
  - The direction and denominator of each metric.
  - An empty answer loses on recall and completion.
  - A failed case stays in the denominator.
  - No applicable denominator gives `N/A`.
  - Duplicate families across partitions fail.
  - Loading labels from a research or tool caller is refused.
  - `evaluator_hash` changes when a label changes.

## 3. Build

1. Write the case and label schemas and the partition and family checks.
2. Write the sealed label loader and the evaluator hash.
3. Write the metric functions and pooling.
4. Write the case files: the development set plus the validation and final-check stubs. The
   labels go to the evaluator-only path, **drafted for human review**.

## 4. Test

```bash
uv run pytest -q tests/evaluation/test_scoring.py
uv run ruff check . && uv run ruff format --check . && uv run mypy src/episalpha && uv run pytest -q -m "not live"
```

Acceptance:
- [ ] Correct metric direction and denominators.
- [ ] Empty answers cannot win by avoiding claims.
- [ ] Failed cases remain in the denominator.
- [ ] Cross-partition duplicate families fail.
- [ ] Labels cannot be loaded through research tool paths.
- [ ] **Owner checkpoint:** a human validates the labels before they become frozen evaluator
      inputs. Record who did it and when.

## 5. Diagnose

- [ ] `diagnose.py`: no regression.
- [ ] Record the evaluator hash and label hash in the journal; these are the frozen identities.

## 6. Stop and hand off

- **BLOCKED if:** the labels are not human-validated (the task can only reach DONE_OFFLINE), or
  the pre-repair numbers are not recorded.
- **Record:** M6 `PROGRESS.md`, `STATUS.md`, and the journal.
- **Next:** M6-T02.
