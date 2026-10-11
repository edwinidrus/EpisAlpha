# M8 constitution: continuous, gated skill learning

Inherits [../CONSTITUTION.md](../CONSTITUTION.md), especially section VIII. The articles below
add to it and never relax it.

1. **Learn offline, act frozen.** No skill changes while a run is executing. The loop runs between
   runs, on the host. The worker never sees an unapproved skill.
2. **Proposals are hostile input.**
   - A proposal is model output shaped by untrusted source text.
   - It is read under M3 constitution article 14: regular files only, no symlinks, size caps,
     schema validation.
   - It is screened deterministically before anything else looks at it.
3. **Screening is deterministic and explainable.**
   - Every rejection names a rule and the offending substring.
   - No LLM judge decides admission. LLM judges miss poisoned distilled skills, so an LLM
     review may only *add* a warning, never clear one.
4. **Skills are procedural, never factual.** They contain no universe tickers or issuer names,
   no dated facts, no numbers with units, no URLs, and no tool names outside the EpisAlpha
   allowlist. A skill says *how* to research, never *what is true*.
5. **Evaluation is paired, frozen and honest.**
   - The current promoted set is compared with that set plus the candidate.
   - Both run on identical snapshots, budgets and cases, using M6 scoring and labels.
   - The candidate must show zero violations and no regression on any metric, plus a gain on
     the metric it targets.
   - Rejection is a valid result. Searching until something passes is forbidden.
6. **A human approves every promotion.**
   - The approver sees the skill text diff, its provenance (runs, trajectories, span IDs), the
     screening report and the evaluation report.
   - The approval records who, when and the content hash.
7. **Everything is versioned and append-only.**
   - Skills are `<id>@v<n>`, immutable once written.
   - The ledger records every state change, including quarantine, rejection and revocation.
   - Nothing is deleted.
8. **Revocation cascades.**
   - Revoking a skill, a run or a source document revokes every skill whose provenance
     includes it.
   - The next run's skill set and hash reflect the revocation.
9. **Temporal honesty.**
   - A skill becomes available at `promoted_at`.
   - Historical-reconstruction runs use only skills promoted at or before their research
     cutoff.
   - Forward runs use the latest promoted set.
10. **Budget realism.** One candidate evaluation costs about 96 live requests. Evaluations are
    batched and scheduled against the free-tier cap, and paused, never truncated, when the cap
    is reached.
11. **The loop is observable.** These events are emitted:
    - `skill.proposed`
    - `skill.screened`, with the rule IDs
    - `skill.evaluated`, with per-metric numerators and denominators
    - `skill.promoted` / `skill.rejected` / `skill.revoked`, with the actor

    No skill text is logged; log its hash.
