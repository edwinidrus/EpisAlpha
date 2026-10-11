# Gate G8: continuous, gated skill learning

**Status:** not started. It depends on G7.

## Commands

```bash
uv run pytest -q tests/learning
uv run episalpha skills list
uv run python scripts/diagnose.py
# plus the four standard checks, and one live evaluation of one real candidate
```

## Criteria

- [ ] Proposals from real runs are harvested with full provenance (run ID, stage, trajectory
      hash, span IDs).
- [ ] Each of these is quarantined, with the rule named (**A30**):
      - a poisoned proposal (an injected instruction, an exfiltration pattern, invisible
        Unicode);
      - a factual proposal (a ticker, dated fact, number with unit, or URL);
      - an off-allowlist tool name.
- [ ] Paired evaluation reuses M6 scoring. A regression rejects; no targeted gain rejects.
      Rejection is recorded as a valid result.
- [ ] Promotion requires a recorded human approval. No code path promotes without it.
- [ ] A revoked skill, or a skill derived from a revoked source, is absent from the next run's
      skill set, and that run's skill-set hash changes (**A31**).
- [ ] A historical run uses only skills promoted at or before its cutoff.
- [ ] One real candidate has gone end to end: proposed → screened → evaluated live → owner
      decision recorded. Whether it was promoted or rejected, the outcome is honest.
- [ ] The `skill.*` spans reconstruct the life of every skill (Phoenix or `spans.jsonl`).
- [ ] A real `diagnose report` lists AI and non-AI failure clusters with trace IDs. At least one
      evaluated candidate cites a cluster as provenance (M8-T05).

## Results log (append-only; real output only)

_No runs yet._
