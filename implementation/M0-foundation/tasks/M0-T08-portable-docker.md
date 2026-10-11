# M0-T08 — Portable offline Docker stack (A15)

| Field | Value |
|---|---|
| Status | DONE |
| Depends on | M5-T03 |
| Phase constitution | [../CONSTITUTION.md](../CONSTITUTION.md) (inherits [global](../../CONSTITUTION.md)) |
| Plan source | A15 spec §3: `docs/superpowers/specs/2026-10-11-portable-docker-design.md`; plan Tasks 1–3: `docs/superpowers/plans/2026-10-11-portable-docker.md` |
| Journal | `tasks/M0-T08-portable-docker.journal.md` |

## 0. Context to load

- `implementation/CONSTITUTION.md`
- `implementation/M0-foundation/CONSTITUTION.md`
- this pack and its journal
- A15 spec §3 and plan Tasks 1–3, with the controller amendments recorded below
- `Dockerfile`, `.dockerignore`, `.gitattributes`, `compose.yaml`, `compose.dev.yaml`, `compose.live.yaml`
- `tests/integration/test_container_files.py`, `tests/integration/test_compose_config.py`,
  `tests/integration/test_cli_research.py`
- `HANDOFF.md` §§3–4, `README.md` Docker block, `docs/implementation/progress.md` A15

Contract excerpts:

> Relative mounts only; container working directory `/app`; the shared network anchor `net`
> owns the only published ports, reachable from the host's loopback only. (A15 spec §3)

Controller amendments supersede the initial plan: editable project install and only
`tests/fixtures/runtime/` as runtime data; networkless, limited-capability root `init`
prepares three directories non-recursively; host ports are overridable; dev `check`
expects `diagnose: PASS`, not a fixed count (compose plugin absent in-container).

## 1. Plan

- **Goal:** locally built runtime/dev images support portable offline UI, CLI, Phoenix,
  fixture research and host-visible Obsidian export.
- **In scope:** image/build-context/LF rules, relative mounts, shared namespace, init,
  dev override, docs and M0-T08 records.
- **Out of scope:** live `compose` sandbox topology and G3 recheck (M3-T05), registry/CI,
  macOS/Windows owner checks, rootless/userns-remap setup.
- **Files:** image and compose files listed above; their three integration tests; docs,
  phase PROGRESS/STATUS, this pack/journal and generated diagnose records.
- **Consumes:** fake-runtime fixtures under `tests/fixtures/runtime/`; existing CLI
  seed/research/replay/export; existing Phoenix configuration.
- **Produces:** `episalpha-app:local`, `episalpha-app:dev`, network `episalpha-app`,
  volume `episalpha-stages`, runtime `init`/`net`/`ui`/`phoenix`/`cli`/`setup-worker`
  services and dev-only `check`.
- **Do not:** ship credentials/local data or the rest of tests; mount the socket by
  default; recursively chown existing data; claim fixtures as live evidence.

## 2. Verify (before building)

- [x] Tasks 1–2 verified the existing CLI/fixtures and compose interfaces; see journal.
- [x] Four host checks green before docs: `619 passed, 8 deselected` (Task 2 evidence).
- [x] Task 1 static tests and Task 2 compose/init tests observed RED then GREEN;
  the missing-settings CLI regression already passed (no CLI code change needed).
- [x] Owner approved A15 and local commits; no live-call approval consumed.

## 3. Build

1. Build pinned runtime/dev targets, editable app and fake-runtime data only.
2. Add portable base/dev orchestration, limited init and live socket overlay header.
3. Document setup/limits; record A15 and completed M0-T08; queue M3-T05 and reopen G3.

## 4. Test

```bash
uv run pytest -q tests/integration/test_container_files.py
uv run pytest -q tests/integration/test_compose_config.py
uv run ruff check . && uv run ruff format --check . && uv run mypy src/episalpha && uv run pytest -q -m "not live"
```

Acceptance (Task 1 Step 8, amended by Fix round 1; Task 2 Step 7, amended by Answers 1–3):
- [x] Both image builds succeed; runtime `episalpha --version` prints `0.1.0`.
- [x] Import resolves to `/app/src/episalpha/__init__.py`; completion fixture exists;
  credentials, git metadata and `tests/conftest.py` are absent from runtime image.
- [x] Dev tools print pytest/ruff/mypy versions.
- [x] Compose builds and starts; init exits 0; UI health `ok`, Phoenix HTTP `200`;
  only loopback listeners (host Phoenix port 6007 during verification).
- [x] Seed succeeds; supported fake run is labeled `[FIXTURE]` and `RESEARCH_COMPLETED`.
- [x] Nine-file export has `conflicts: 0`, visible at `.episalpha/exports/vault/generated/`.
- [x] Dev build/check reports `diagnose: PASS`; observed `611 passed / 8 skipped` is
  evidence, not a fixed-count requirement.
- [x] Old toolbox volumes confirmed absent; historical cleanup errors retained in journal.
- [ ] macOS Apple Silicon and Windows Docker Desktop owner build/check/fake/live sequence.

## 5. Diagnose

- [x] `uv run python scripts/diagnose.py` passes with regressions 0 and orphans 0;
  summary recorded in journal and M0 PROGRESS.
- Expected runtime evidence: Task 2 fixture trace ID is recorded in the journal;
  Phoenix trace-list check was skipped (`otlp_endpoint` unset), not claimed passed.
  No new spans are expected from this documentation task.
- [x] One journal Attempt block records Tasks 1–2 evidence and Task 3 continuation.

## 6. Stop and hand off

- **BLOCKED if:** offline acceptance or diagnose fails; scope requires an unapproved change.
- **Record:** [phase PROGRESS](../PROGRESS.md), [STATUS row](../../STATUS.md) and journal.
- **Next:** M3-T05 (`compose` sandbox topology and owner-approved live check); G3 reopened.
