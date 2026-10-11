# M4 phase report: end-to-end research, CLI and replay

**Gate G4: PARTIAL on 2026-10-11.** The complete vertical slice works on the fake runtime and is
wired to the real Hermes runtime. The three real-case quality reviews (M4-T04) are **BLOCKED**
on the G2 owner checkpoint: the demo cases are still PROVISIONAL until their filings are ingested
and inspected by hand.

## What M4 delivers

| Task | Status | What exists now |
|---|---|---|
| M4-T01 | DONE | `ResearchRunner`: admission, atomic claim, cancel flag, 8 stages, canonical ID mapping, per-stage validation, one bounded repair, honest terminal states, hashed artifacts, one trace per run |
| M4-T02 | DONE | CLI: `demo seed`, `research run/status/execute/cancel`, frozen exit codes; logic in `research/services.py` |
| M4-T03 | DONE | `replay` (tamper-evident, zero calls), `research recover` (new attempt, completed stages reused), snapshot lineage |
| M4-T04 | **BLOCKED** | Real-case reviews wait for the G2 owner checkpoint and your approval of ~24 requests |

## Commands that work now

```bash
uv run episalpha demo seed
uv run episalpha research run --case supported --runtime fake      # [FIXTURE], exit 0
uv run episalpha research run --case conflicting --runtime hermes  # abstains: no filings ingested yet
uv run episalpha research status RUN_ID
uv run episalpha research cancel RUN_ID
uv run episalpha research recover RUN_ID
uv run episalpha replay RUN_ID                                     # verifies every artifact
```

Exit codes: 0 completed · 2 invalid usage · 3 rejected · 4 failed or timed out (replay:
integrity error) · 5 abstained or partial · 6 cancelled.

## What the tests prove (fake runtime, synthetic snapshot)

- Every terminal state is reached for its real reason: completion, abstention (no evidence,
  or a synthesized abstain), repaired-once, unrepairable → `REJECTED`, provider failure →
  `FAILED` (never `ABSTAINED`), timeout, cancellation (scripted or requested), partial.
- Admission is idempotent; a second active job and a double claim are refused; a model cannot
  take over an existing canonical ID.
- Replay makes no model, relay, runtime or connector call, and catches a one-byte flip as well
  as a consistent edit of artifact *and* index (cross-checked against SQLite).
- A crash mid model call stays visible as a `started` attempt; `recover` reruns only from the
  interrupted stage.

## Bugs found and fixed along the way

1. **`Repository.update_run` wiped history** (M2-T01 code): `INSERT OR REPLACE` deleted the run
   row, and `ON DELETE CASCADE` silently removed its stage results and lease on every state
   change. Now an `UPDATE`; regression test added.
2. **Artifact index only written at the end:** a crashed run left nothing verifiable. The index
   is now updated with every artifact.
3. **CLI error exits leaked a tracer** into the next command or test.

## Numbers

| Measure | Before M4 | After |
|---|---:|---:|
| Default suite | 504 | 553 |
| Source files under strict mypy | 32 | 35 |
| Database schema version | 1 | 2 (additive: lease and cancel tables) |
| Live model requests | — | 0 (M4 is fully offline) |

## Deviations (in the journals)

- A new `research/services.py` keeps logic out of the CLI (M4 article 8).
- Lineage (`prior_run_id`) lives in `submission.json` and the artifact index, not in
  `RunRequest`, avoiding a contract change.
- The fake scenario can be overridden with `EPISALPHA_FAKE_SCENARIO`; the CLI interface itself
  is unchanged.
- Red-first slipped once more (M4-T02: services and CLI before their tests).

## Owner actions

1. **G2 checkpoint:** ingest and hand-inspect the LULU, TSCO and CALX filings, then confirm or
   reassign each case.
2. **Approve the M4-T04 real runs** (≤ 24 requests), then review them in
   `docs/implementation/demo_acceptance.md`.
