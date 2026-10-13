# Demo acceptance (M7-T02)

What the v0.1 demo is proven to do, how, and what is still open. Offline and live evidence are
reported separately (M7 article 2). Updated 2026-10-13.

## One command

```bash
uv run python scripts/demo_smoke.py
```

Clean-copy rehearsal on 2026-10-13 (tracked and new files only, no `.episalpha/`, no `.env`,
no credentials): `uv sync --all-groups`, then the smoke:

```text
[FIXTURE] fake runtime: every run below is scripted fixture output, not research
ok seed
ok run supported: run-… RESEARCH_COMPLETED
ok run conflicting: run-… RESEARCH_COMPLETED
ok run insufficient: run-… ABSTAINED
ok replay (3 runs, network blocked)
ok export (126 links, all resolve)
ok experiment: baseline_retained
ok backup (93 files hashed)
ok restore (hashes verified; replay from the restored copy)
replay after warm-up: 0.28 s
total: 4.7 s
smoke: PASS
```

Performance target (plan section 14): the saved corpus opens in 5 s or less after warm-up.
Measured: 0.28–0.30 s per saved replay on the WSL2 development machine. Live research within the
300 s budget was measured in M3 (traces `279e56da…`, `f8c7b412…`), not here.

`--inject-failure` edits one saved artifact before the replays; the smoke then fails with
`INTEGRITY_ERROR` and exit 1 (`tests/integration/test_smoke_script.py`).

## Acceptance rows

All automated rows are in `tests/integration/test_demo_acceptance.py` (offline, fake runtime or
stdlib fake worker; never evidence of a live run). The row-to-test map is in
`implementation/M7-acceptance/tasks/M7-T01-acceptance-suite.journal.md`.

| Rows | Offline | Live or manual part |
|---|---|---|
| A01–A08, A10, A12–A14, A16–A26, A29 | PASS | — |
| A09 worker isolation | PASS (worker command) | live boundary probe passed in M3 (`test_runtime_boundary.py`, owner-approved) |
| A11 browser refresh | PASS (AppTest) | manual: a real browser refresh (M7-T03) |
| A15 Obsidian export | PASS (byte-stable, links resolve, annotations kept) | manual: Obsidian opens the vault (G5, owner) |
| A27 relay egress fields | PASS (HTTP front on loopback) | live route probed in M0-T04 |
| A28 Hermes learning writes | PASS (fake worker) | real Hermes run without learning writes: M3 live runs |
| A32 one trace, metadata-only fallback | PASS (Phoenix down) | a trace in a running Phoenix: `test_phoenix_export.py` (live marker) |
| A30–A31 | — | M8, verified at G8 |

## Definition of done (plan 15.1)

| Item | State |
|---|---|
| G0–G7 have recorded results | G0–G3 PASSED; G4, G5, G6 PARTIAL; G7 pending M7-T03 |
| Three curated cases and synthetic adversarial cases | Cases exist, PROVISIONAL until the G2 checkpoint; synthetic cases exist |
| Browser: research, evidence, knowledge, experiments | Done |
| CLI: seed, run, inspect, cancel, recover, replay, export, compare | Done |
| One real Hermes/provider integration at the pinned version | Done in M3 (live runs, owner-approved) |
| Payloads, text, spans, manifests traceable | Done |
| Typed references for every material assertion | Done |
| Unknowns, review status, contradictions visible | Done |
| Snapshot boundaries obeyed | Done |
| Saved replay network-free, distinct from fresh inference | Done |
| Agent cannot modify canonical data, evaluator, labels, harness | Done offline; live boundary from M3 |
| Obsidian links valid, annotations preserved | Automated part done; Obsidian app check open |
| One actual bounded challenger experiment, honest report | **Open**: only the fake campaign ran; live campaign BLOCKED (capacity decision, label review, 12 missing cases) |
| Default suite offline without credentials | Done |
| README and demo script work from a clean checkout | Done (rehearsal above) |
