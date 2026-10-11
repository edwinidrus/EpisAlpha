# M3-T05 — Compose sandbox topology (A15)

| Field | Value |
|---|---|
| Status | DONE |
| Depends on | M0-T08 |
| Phase constitution | [../CONSTITUTION.md](../CONSTITUTION.md) (inherits [global](../../CONSTITUTION.md)) |
| Plan source | A15 plan Tasks 4–6 (docs/superpowers/plans/2026-10-11-portable-docker.md); spec §4 |
| Journal | [M3-T05-compose-topology.journal.md](M3-T05-compose-topology.journal.md) |

## 0. Context to load

- `implementation/CONSTITUTION.md`
- `implementation/M3-runtime/CONSTITUTION.md`, articles 6–8, 10–11
- This pack and its journal
- `docs/superpowers/specs/2026-10-11-portable-docker-design.md` §4
- `docs/superpowers/plans/2026-10-11-portable-docker.md`, Tasks 4–6
- `src/episalpha/runtime/sandbox.py`, `src/episalpha/research/services.py`
- `tests/runtime/test_sandbox.py`, `tests/runtime/test_sandbox_services.py`,
  `tests/integration/test_runtime_boundary.py`

Contract excerpts (spec §4.3):

> The worker network is `--internal` with `inhibit_ipv4`: the host has no address on it.
> The forwarder is the worker's only neighbour and forwards exactly two fixed ports; it takes
> no routing input from the worker.
> The provider key lives only in the relay. The worker never mounts the data root, the canonical
> database, labels, `.env` or the Docker socket.

## 1. Plan

- **Goal:** preserve the M3 isolation boundary in both sandbox topologies, and exercise the
  compose worker → forwarder → relay/MCP path with a real provider on Linux.
- **In scope:** topology selection, fixed compose network/name/stage volume, per-stage
  sub-paths, Docker preflight before admission, runtime wiring, boundary probes, live
  evidence, A15 constitution wording, G3 re-run and task records.
- **Out of scope:** new sandbox backends, rootless/userns-remap configuration, owner
  macOS/Windows checks, G2 real-filings ingestion and thesis quality review; fixing the
  after-admission runtime-assembly QUEUED stranding.
- **Files (Tasks 4–6):** `src/episalpha/runtime/sandbox.py`,
  `src/episalpha/research/services.py`, `config/runtime.lock.json`, the three tests above;
  M3/M5 constitutions, M3 pack/journal/GATE/PROGRESS, `implementation/STATUS.md`,
  `HANDOFF.md` §4, `docs/implementation/progress.md`, regenerated
  `implementation/DIAGNOSTICS.md` and `implementation/logs/diagnose.jsonl`.
- **Consumes:** M0-T08 compose namespace `episalpha-app`, anchor `net`, stage volume
  `episalpha-stages`; pinned worker image and existing hardened launcher/host reader.
- **Produces:** compose topology runtime/readiness integration, per-stage volume mounts,
  honest Linux boundary/live evidence, G3 A15 re-run result; next task M5-T04.
- **Do not:** weaken hardening, uid/symlink/allowed-set assertions; expose secrets or the
  Docker socket to the worker; claim macOS/Windows or a completed compose live thesis;
  relabel provider failure. No live rerun in Task 6: controller supplied approved evidence.

## 2. Verify (before building)

- [x] Task 4 tested the missing compose interfaces first: expected
  `ImportError: cannot import name 'COMPOSE_STAGE_ROOT'`; then 16 sandbox tests passed.
- [x] Task 5 mount guard and readiness tests failed before their fixes, then passed.
- [x] Task 4 final checks recorded 628 passed; Task 5 final checks recorded
  632 passed, 8 deselected. Task 6 Step 4 freshly confirms 632 passed, 8 deselected.
- [x] Owner approved controller live Attempts A and C; the controller supplied their
  exact outputs, recovery Attempt B, and the no-leftovers check. Steps 2–3 skipped here.
- [x] Controller Answer 1 authorizes this fresh pack and the exact article-8 sub-bullet
  because the supposed stub/replacement target did not exist.

## 3. Build

1. Task 4: implement host/compose selection, named forwarder target, per-stage volume
   sub-paths and Docker preflight; preserve host behavior and hardening.
2. Task 5: reject root/traversal volume mounts; wire readiness and runtime configuration;
   probe both topologies, passing the actual host home into compose.
3. Task 6: add the exact M3 article-8 sub-bullet and M5 article-9 wording; quote controller
   live evidence and Task 5 verdicts; append G3 results without changing earlier blocks.
4. Record DONE in this pack, journal, M3 PROGRESS and STATUS; retain open owner checks,
   document rebuild/recovery and QUEUED stranding; run four checks and full diagnose.

## 4. Test

Fresh Task 6 commands (offline only):

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy src/episalpha && uv run pytest -q -m "not live"
uv run python scripts/diagnose.py
```

Acceptance (Task 4–6 checks; outputs in journal and G3):
- [x] Host topology behavior/hardening retained; compose uses fixed name/network and
  volume sub-paths, not host stage binds. Offline sandbox tests cover both.
- [x] Preflight refuses unknown topology or missing socket before admission; compose
  assembly uses the shared namespace and `/stages`.
- [x] Volume root and parent traversal refused in both mount positions.
- [x] Both Linux boundary probes pass (3 tests each): only `relay_via_forwarder`
  ALLOWED; host home, `/stages`, repository, canonical DB, Docker socket and unrelated
  egress BLOCKED; uid 10001; existing symlink/hardening assertions unchanged.
- [x] Cancel/timeout stop the worker within 10 s in both topologies, measured in Task 5.
- [x] Owner-approved real-provider compose path exercised worker + relay + tool server:
  RESEARCHING and CRITIQUING completed; SYNTHESIZING failed provider-side,
  `SOURCE_FAILED`; 7 requests, 4 tool calls; no leftover worker/forwarder.
- [x] Exact A15 constitution wording and rebuild/recovery guidance recorded; G3 dated
  append-only re-run, STATUS/PROGRESS links, and M5-T04 next-task pointer.
- [x] Final four offline checks pass: 83 files formatted, mypy 38 source files,
  `632 passed, 8 deselected in 16.08s`.

## 5. Diagnose

- [x] Full `uv run python scripts/diagnose.py` passes after the records are complete:
  632 passed, failures 0, regressions 0, orphans 0; real output in the journal.
- Controller `model.call` evidence: six successful calls served_by Nvidia; seventh HTTP
  200 body rejected as `SOURCE_FAILED`. Trace `1c8801aa415db157bc92bbcc1046dd4d` is
  JSONL only (`otlp_endpoint` unset), not a new Phoenix pass. Earlier G3 Phoenix evidence
  is retained.
- [x] One journal Attempt block records Task 4–6 evidence and its provenance.

## 6. Stop and hand off

- **BLOCKED if:** topology isolation or runtime infrastructure remains broken, outputs
  cannot be substantiated, or four checks/full diagnose fail. Provider-side failure is
  recorded honestly, not an infrastructure pass or a completed thesis.
- **Record:** this pack, journal, M3 PROGRESS, STATUS, G3, diagnostics and history.
- **Next:** M5-T04.
- **Open limits:** no completed live thesis in compose yet; macOS/Windows owner checks
  pending; rootless Docker / userns-remap owner TODO. Supported case abstained because
  real filings are not ingested (G2 owner checkpoint).
