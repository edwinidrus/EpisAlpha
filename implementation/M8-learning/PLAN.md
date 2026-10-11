# M8 plan: continuous, gated skill learning (post-v0.1)

**Goal:** the research model gets better over time by accumulating *procedural* skills, safely.
Every skill is proposed by a run, screened deterministically, evaluated offline against fixed
cases, approved by the owner, and only then used read-only by later runs. Every skill is
revocable.

**Plan source:** amendments A12 and A13 (2026-10-10). This phase reuses M6 (cases, scoring,
campaign runner, the ledger pattern in `evolution/candidates.py`) and the M3/M4 hooks
(`propose_skill`, the read-only skills mount, the skill-set hash on every run).

## Why, and why gated

- **Procedural skills help weaker models most.** One 2026 study measured up to +14.2 points for
  a smaller model against +3.1 for a larger one. The research model is not frontier-class.
- **Uncurated self-generated skills hurt.** SkillsBench: curated skills +16.2 points,
  self-generated −1.3 points.
- **Self-evolving skill pipelines can be poisoned.** In SkillJack (arXiv 2608.03509), poisoned
  trajectories distilled into skills slipped past an LLM judge 88.6% of the time, and most
  triggers survived deletion of the source. Hence: provenance, deterministic screening,
  evaluation, human approval and cascade revocation.
- **Hermes' native learning stays off.** That covers background review, memory, curator and the
  Hub. They write unprovenanced state and spend unbudgeted requests.

## Grounding (A14)

M8-T05 reads what the whole system actually did: local Phoenix traces of runner, connectors,
tools, model calls, validator and sandbox, plus your span annotations. It clusters the failures
and costs into a deterministic report. Its clusters become *improvement targets* that a skill
proposal or an M6 hypothesis can cite as provenance. Phoenix annotations are never evaluation
labels.

## Flow

```text
run N:   Hermes (skills RO) ──propose_skill──▶ run artifacts (data, with run_id + span IDs)
M8-T02:  harvest → deterministic screen → quarantined | candidate
M8-T03:  paired offline evaluation: promoted set vs set + candidate (M6 cases and scoring)
M8-T04:  owner reviews diff + provenance + screen + eval → approve | reject
run N+1: promoted set mounted RO; skill-set hash in harness hash; revocable at any time
```

## Tasks

| Task | Title | Status | Depends on | Pack |
|---|---|---|---|---|
| M8-T01 | Skill library and ledger | TODO | G7 | [pack](tasks/M8-T01-skill-library.md) |
| M8-T02 | Harvest and deterministic screening | TODO | M8-T01 | [pack](tasks/M8-T02-screening.md) |
| M8-T03 | Offline paired skill evaluation | TODO | M8-T02 | [pack](tasks/M8-T03-evaluation.md) |
| M8-T04 | Promotion, revocation, temporal availability | TODO | M8-T03 | [pack](tasks/M8-T04-promotion.md) |
| M8-T05 | Trace-grounded improvement backlog (A14); may run first | TODO | G7, M0-T07 | [pack](tasks/M8-T05-trace-backlog.md) |

## Owner decisions

1. **Free-tier capacity.** One evaluation is about 6 validation cases × 2 variants × ≤ 8
   requests, so about 96 requests. At 50 requests/day that is about one candidate every 2 days.
   With at least $10 of lifetime OpenRouter credits (1,000/day), several fit per day. Decide
   before M8-T03 runs live.
2. **Review cadence.** Proposals can accumulate. Pick a rhythm, for example a weekly
   review of the evaluated candidates.
3. **Promotion is always human** (decided 2026-10-10). Auto-promotion is out of scope.

## Out of scope

- Hermes-native memory, user profile, background review, curator and Skills Hub.
- Skills that contain code.
- Cross-user skill sharing.
- Fine-tuning model weights.
