# M6 plan: AVO-inspired research-quality experiment

**Goal:** demonstrate controlled procedural improvement against fixed, evidence-based tasks,
including the possibility that the challenger is rejected.

**Plan source:** plan §12 (12.1 experimental contract, 12.2 candidate surface, 12.3 metrics and
decision rule, M6-T01..T04); A8 (the numeric-correctness metric); acceptance rows A16, A17,
A18 and A24.

## Tasks

| Task | Title | Status | Depends on | Pack |
|---|---|---|---|---|
| M6-T01 | Labeled cases and deterministic metrics | TODO | G5 | [pack](tasks/M6-T01-cases-metrics.md) |
| M6-T02 | Candidate validation and lineage | TODO | M6-T01 | [pack](tasks/M6-T02-candidates.md) |
| M6-T03 | Offline campaign runner | TODO | M6-T02 | [pack](tasks/M6-T03-campaign.md) |
| M6-T04 | Experiment report and browser comparison | TODO | M6-T03 | [pack](tasks/M6-T04-report.md) |

## Dataset contract (plan §12.1)

- 24 small human-reviewed cases:
  - 12 development cases, labels visible for failure analysis;
  - 6 validation cases, labels for the evaluator only;
  - 6 final-check cases, inputs and labels withheld until the configuration is frozen.
- Group by source, document and event family before splitting; no near-duplicates across
  partitions.
- Required case types: extraction, source attribution, numerical units and periods,
  contradiction, duplicate lineage, missing evidence, future evidence, and injected instructions.
- This is engineering machinery testing, **not** statistical proof.

## Decision rule (plan §12.3, frozen per campaign before validation)

1. Zero temporal, reference and boundary violations in both variants.
2. No new unsupported material claims. No drop in pooled supported-claim precision,
   required-fact recall, correct abstention or completion.
3. At least one more distinct labelled contradiction recovered across the validation cases, with
   none of the baseline's recoveries lost.
4. Mean requests and median latency at most 1.5× baseline, and every run within its hard
   budget.
5. On final-check cases, after validation passes: valid, with no regression. A second
   improvement is not required.

If any condition fails, the baseline is retained.

## Owner decisions needed before M6-T03 runs live

1. **Free-tier capacity.**
   - At most 8 requests per run, across 2 variants, 6 validation and 6 final cases, with 2 fresh
     runs each "if budget allows". That is roughly 100–200 requests.
   - At 50/day this is a 2–4 day campaign. With $10 or more of lifetime credits (1,000/day) it
     fits in one day.
   - Decide, and record the decision in `PROGRESS.md`.
2. **Label review.** A human validates all labels before they freeze (M6-T01 owner checkpoint).
