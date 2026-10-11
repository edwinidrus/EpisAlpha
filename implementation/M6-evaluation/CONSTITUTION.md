# M6 constitution: AVO-inspired research-quality experiment

Inherits [../CONSTITUTION.md](../CONSTITUTION.md). The articles below add to it and never relax it.

1. **Research quality, never returns.** The experiment optimizes evidence-based research quality
   only. There is no return optimization, no alpha claim and no financial conclusion.
2. **Labels are sealed.**
   - Validation and final-check labels live at an evaluator-only path, outside every agent- or
     candidate-accessible path.
   - Only the evaluator loads them. Research tools and the candidate author cannot.
3. **Exactly one mutation.**
   - The only permitted patch is `replace /contradiction_search → true` on the baseline config.
   - There is no arbitrary code, and no change to evaluator, labels, partitions, budgets,
     timestamps, schemas, permissions or evidence.
4. **The evaluator never executes candidate code.** Candidates are data (JSON patches),
   validated by a strict schema.
5. **The rule is declared before the data.**
   - The plan §12.3 decision rule is frozen in the campaign manifest before any validation
     result is seen.
   - The owner may change thresholds only before a new campaign, with a new manifest version.
6. **Omission cannot win.**
   - Failed and empty cases stay in denominators.
   - A metric with no applicable denominator is `N/A`, never 0 or 1.
   - One metric never substitutes for another.
7. **Every trial is kept.** Failed, abandoned and interrupted trials stay in the ledger, and the
   report shows them.
8. **Rejection is a valid result.** A challenger that does not clear the rule is reported as
   rejected; the baseline is retained, and the milestone can still pass. Searching until a
   favourable result appears is forbidden.
9. **Fake never satisfies live.** Execution identities include:
   - runtime mode;
   - provider/model;
   - snapshot;
   - harness/config;
   - evaluator and label hashes;
   - attempt.

   Fake and real campaigns never share an execution ID.
10. **Hash-locked inputs.** A change to evaluator or label hashes blocks comparison until it is
    re-declared (acceptance row A24).
11. **Budget realism (A9).** The free tier gives 50 requests/day, or 1,000/day with $10 or more
    of lifetime credits. A campaign of about 100 or more requests needs either credits or a
    recorded multi-day schedule. That is an owner decision before M6-T03 runs live. Never cut
    cases to fit the cap without recording it as a limitation.
12. **Evaluation is observable (A11, A14).** Each trial emits an `EVALUATOR` span, linked to its
    run trace:
    - `eval.trial`, with `campaign_id`, variant, `case_id`, `execution_id`, terminal state and
      metric numerators/denominators;
    - `eval.decision`.

    **No label content ever enters a span or Phoenix.** Spans carry scores and counts only.
