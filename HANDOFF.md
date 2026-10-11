# EpisAlpha handoff

**Date:** 2026-10-11 · **Stopped after:** M5-T01 (DONE) · **Next task:** M5-T02 · **Branch:** `main`

This file is for whoever continues EpisAlpha on another machine, human or coding agent. It
covers four things: where the build stands, how to bring it up anywhere with Docker, what is
blocked on the owner, and the working rules. It supersedes `SESSION_HANDOFF.md` (2026-09-20,
kept for history).

---

## 1. Read first

| Order | File | Why |
|---:|---|---|
| 1 | `CLAUDE.md` | Repository rules. Claude Code loads it automatically. |
| 2 | `implementation/README.md` | Session protocol: one task per session; Plan → Verify → Build → Test → Diagnose. |
| 3 | `implementation/STATUS.md` | Source of truth for task status and the next-task pointer. |
| 4 | `implementation/CONSTITUTION.md` + the phase `CONSTITUTION.md` | Binding rules. A phase constitution can only add rules. |
| 5 | The next task pack: `implementation/M5-browser-obsidian/tasks/M5-T02-evidence-graph.md` | The work. |
| 6 | Plan `EpisAlpha_MVP_Milestone_Implementation_Plan.md` | Only at the sections a pack cites. Never load the blueprint by default. |

Each phase folder has a `REPORT.md` (M0–M4) with what was built, verified, found and left open.

---

## 2. Where the build stands

| Phase | Gate | State |
|---|---|---|
| M0 Foundation | G0 **PASSED** | OpenRouter route verified live; `scripts/diagnose.py`; OpenTelemetry tracing; local Phoenix. |
| M1 Contracts | G1 **PASSED** | Frozen contracts, temporal policy, validator, derivation recomputation (A8). |
| M2 Evidence | G2 **PASSED** | SQLite + object store, snapshots, point-in-time XBRL, traced connectors. The owner checkpoint (live ingestion + hand inspection) is still open. |
| M3 Runtime | G3 **PASSED** | Pinned Hermes 0.21.3 (`c1488ac`) over MCP; model relay with stage policy; hardened worker container. Live runs proven (traces `279e56da…` local, `f8c7b412…` container). |
| M4 Research CLI | G4 **PARTIAL** | Runner, CLI, replay, recovery done. **M4-T04 BLOCKED**: real-case reviews need the G2 checkpoint. The owner chose to continue anyway. |
| M5 Browser + Obsidian | — | **M5-T01 DONE** (Streamlit research view). T02 evidence graph, T03 Obsidian export, T04 owner walkthrough: TODO. |
| M6 Evaluation | — | Not started. |
| M7 Acceptance | — | Not started. |
| M8 Learning (post-v0.1) | — | Not started. Depends on G7. |

**Last verified (2026-10-11):**
- Host: four checks green, `570 passed, 8 deselected`.
- Inside the Docker app image (`docker compose run --rm check`): `diagnose: PASS | tests
  {'passed': 570, 'failed': 0, ...} | failures 0 | regressions 0 | orphans 0 | 69.1s`.

**Live model budget.** About 28 of the 40 requests the owner approved for the overnight session
were used. That approval was for that session only. **Any new live call needs fresh owner
approval.** The free tier allows 20 requests/min and 50/day (1,000/day with ≥$10 lifetime credit).

---

## 3. Bring it up on a new machine (Docker)

Prerequisites: Docker Engine >= 26 with Compose >= 2.24 (Docker Desktop on macOS or Windows, or
Docker Engine on Linux). Then, from the repository root:

```bash
cp config/demo.example.toml config/demo.toml   # Windows PowerShell: Copy-Item
# put the credentials into .env (names only are listed in config/demo.toml)
docker compose build
docker compose up -d                            # UI http://127.0.0.1:8501, Phoenix :6006
docker compose run --rm cli demo seed
docker compose run --rm cli research run --case supported     # a [FIXTURE] fake run
docker compose run --rm cli replay <run_id>
docker compose run --rm cli export obsidian --run <run_id>     # vault: .episalpha/exports/vault
docker compose -f compose.yaml -f compose.dev.yaml run --rm check   # expect diagnose: PASS
```

On Linux, if your uid/gid are not 1000, set EPISALPHA_UID and EPISALPHA_GID (for example in
your shell, or in a `.env` next to compose.yaml) so files in .episalpha stay yours.

Before the first dev `check`, build its image with
`docker compose -f compose.yaml -f compose.dev.yaml build`; expect `diagnose: PASS`, not a
fixed test count, because compose tests skip inside the container (no compose plugin).

The one-shot `init` service creates `./.episalpha`, `./.episalpha/phoenix` and
`./.episalpha/exports` and chowns just those directories, non-recursively, to
`EPISALPHA_UID:EPISALPHA_GID` before anything starts, because rootful Docker creates missing
bind sources as root. It runs as root with only CHOWN/DAC_OVERRIDE/FOWNER capabilities and no network.

Host ports are overridable: `EPISALPHA_UI_PORT` (default 8501) and `EPISALPHA_PHOENIX_PORT`
(default 6006); for example, set `EPISALPHA_PHOENIX_PORT=6007` if another project uses 6006.
Known limit: the workbench's "Open trace in Phoenix" link is derived from `otlp_endpoint` and still points at :6006.

Restart the stack with `docker compose up -d` (or `restart` all services); restarting `net` alone leaves ui and phoenix in a dead network namespace.

**Phoenix traces.** To send traces to Phoenix, uncomment `otlp_endpoint` under
`[observability]` in `config/demo.toml`. Without it, spans still go to
`.episalpha/logs/spans.jsonl`.

### How the orchestration is put together

| File | Role |
|---|---|
| `Dockerfile` | Multi-stage runtime/dev app image: digest-pinned Python and Docker CLI, uv, dependencies in `/opt/venv`, project installed editable at `/app/src`. Code is baked in; only `tests/fixtures/runtime/` ships from tests, as the fake runtime's data. `.dockerignore` allowlists the build context, excluding credentials, local data and the rest of the test suite. |
| `compose.yaml` | `init` prepares data directories; `net` owns the shared namespace and loopback-only host ports; `ui`, Phoenix and tools-profile `cli`/`setup-worker` use it. Relative data/config binds and named `episalpha-stages` volume; no Docker socket. |
| `compose.dev.yaml` | Dev image and working-copy mount at `/app`; defines the networkless offline `check` service. |
| `compose.live.yaml` | An overlay that adds the host's Docker socket to `ui`, `cli` and `setup-worker`, for live runs and the worker build only. |
| `scripts/setup_worker.py` | Clones Hermes at the pin, then builds the worker image with the M3-T04 recipe. `--record` writes the new image ID to the lock; `--local-venv` builds the local-launcher venv. |

Three design choices to keep:
- **Relative mounts, fixed container root `/app`.** Run compose from the repository root;
  host and container paths no longer need to match.
- **Shared localhost, loopback-only host exposure.** Only `net` publishes UI/Phoenix ports;
  Phoenix is still `127.0.0.1:6006` inside the shared namespace, so the loopback-only
  `otlp_endpoint` rule is unchanged even if the host port is overridden.
- **Local build only.** Rebuild when code or dependencies change; no startup dependency sync,
  registry distribution or CI publishing. The dev override runs the working copy instead.

### Without Docker (host, as before)

```bash
uv sync --all-groups
uv run ruff check . && uv run ruff format --check . && uv run mypy src/episalpha && uv run pytest -q -m "not live"
uv run streamlit run apps/streamlit_app.py                 # .streamlit/config.toml binds 127.0.0.1
docker compose -f observability/compose.yaml up -d         # Phoenix alone
```

### Carrying the local data (optional)

`.episalpha/` is git-ignored, so it does not travel with the repository. It holds:
- `app.sqlite3`: demo seed plus fake runs;
- `objects/` and `runs/`: payloads and run artifacts;
- `phoenix/`: traces, including the M3 live runs cited in the gate logs;
- `vendor/`: the Hermes clone and venv, which `setup_worker.py` rebuilds.

Nothing in it is irreplaceable: no real filings have been ingested yet. To keep the traces and
runs, copy them across:

```bash
tar czf episalpha-data.tgz --exclude=.episalpha/vendor .episalpha     # old machine
tar xzf episalpha-data.tgz                                            # new machine, repo root
```

---

## 4. Live Hermes runs on the new machine

Each step needs the owner. Each live run spends model requests.

**Run `setup-worker` once per machine (and `--record`). This machine has no
`episalpha-worker` image yet.** The app build does not build the Hermes worker; the lock
(`config/runtime.lock.json` → `hermes.worker_image.id`) contains another machine's image ID.
Builds are not bit-for-bit reproducible: record the locally built ID, review the lock diff,
then re-run the G3 live checks before trusting it.

**Pending M3-T05:** the `compose` sandbox topology and live check arrive with M3-T05,
which reopens G3. Until then, live runs still need Linux host mode (`uv run` on the host);
the portable-container live commands below are the intended flow after M3-T05, not a
verified live path today.

Set `DOCKER_GID` to the socket group on Linux (`export DOCKER_GID=$(stat -c %g
/var/run/docker.sock)`), or to `0` on Docker Desktop (owner check still outstanding).

```bash
docker compose -f compose.yaml -f compose.live.yaml run --rm setup-worker   # once per machine
docker compose -f compose.yaml -f compose.live.yaml run --rm setup-worker python scripts/setup_worker.py --record
docker compose -f compose.yaml -f compose.live.yaml up -d
docker compose -f compose.yaml -f compose.live.yaml run --rm cli \
    research run --case supported --runtime hermes   # needs ingested filings, see 5.1
```

**Verified and not verified.** Tasks 1–2 verified the portable offline stack on rootful Linux:
fixture seed/run/export, both loopback health checks and the dev diagnose. No live Hermes
call was made; earlier G3 live evidence is host-side. macOS Apple Silicon and Windows
Docker Desktop build → check → up → fake run → live run, `DOCKER_GID=0` socket access and
the arm64 Hermes build remain owner checks, not claimed passes.

**Security notes:**
- The socket overlay gives the app containers control of the Docker daemon, which is
  root-equivalent on a rootful engine. The worker never gets it.
- G3 left one open item: rootless Docker or `userns-remap`. On the new machine, prefer setting
  that up before live runs.

---

## 5. Owner actions and blockers

1. **G2 checkpoint, which blocks M4-T04.** Ingest the LULU, TSCO and CALX filings (SEC EDGAR,
   fair-access User-Agent with your contact address) and inspect them by hand. Then confirm or
   reassign the three cases, whose mapping is PROVISIONAL in `eval_cases/manifests/`.
2. **Approve the M4-T04 real-case runs**: about 24 free-tier requests.
3. **Docker isolation**: rootless Docker or userns-remap (the G3 TODO). Phoenix auth is off; its
   access control is the loopback binding (`docs/implementation/phoenix.md`).
4. **Reviews still outstanding**:
   - M0 probe findings (G0);
   - M1 serialized examples (G1);
   - Hermes invokes `uv` inside the sandbox (noted in M3);
   - the relay and tool server bind `docker0`.
5. **Owner walkthroughs**: M5-T04 (browser), the M6-T03 live-campaign capacity decision, and
   M7-T03.
6. **EDGAR finding**: `acceptanceDateTime` carries a `Z` and is treated as UTC. Confirm.

---

## 6. Working rules that carry over

- **One task per session, in STATUS order.** Each task ends with three records:
  - a journal entry (`tasks/*.journal.md`, every attempt);
  - a `PROGRESS.md` row with real command output;
  - the `STATUS.md` row.

  Then run `uv run python scripts/diagnose.py` (in Docker: `docker compose run --rm check`).
- **Red first.** Never weaken a test, skip a failure, or regenerate an expected answer.
- **Fixtures stay fixtures.** `FakeRuntime` output is always labelled `[FIXTURE]` and never
  counts as a live pass. A blocked live gate stays blocked.
- **Secrets.** Only `ENV:<name>` references appear in files. Never print `.env` values; read
  names only (`cut -d= -f1 .env`).
- **Commits and pushes are owner actions.** This handoff's commit was explicitly requested.
- **Do not invent upstream facts.** Pin and record what was actually observed.
- **No model names in code.** The research route lives only in `config/*.toml`.

---

## 7. Next steps (in order)

1. **M5-T02**, evidence inspection and the local graph. Reuse `services.run_view`. Render all
   evidence text with `st.text`. Keep the graph under 50 nodes, with a relation table that works
   without the graph.
2. **M5-T03**, the deterministic Obsidian export, then **M5-T04** (owner walkthrough) and gate G5.
3. **M6** (evaluation), then **M7** (acceptance and smoke). **M8** is post-v0.1.

Known gap carried from M5-T01: while a run is in progress, the "Open trace in Phoenix" link
appears only after the run ends, because the runner writes `trace_id` into the index at finish.

Two bugs fixed in M5-T01, both with regression tests:
- A Hermes run that could not start used to hold the single job slot forever.
- `run_usage` turned unknown token counts into a smaller number.
