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

### Requirements
- Linux with **Docker Engine** and Compose **≥ 2.24** (WSL2 with the engine installed works),
  plus git.
- Nothing else. Python, uv and the Docker CLI live in the app image.
- Docker Desktop on macOS or Windows runs the offline stack, but live Hermes runs need host
  networking and a `docker0` gateway (section 4).

### Steps

```bash
git clone https://github.com/edwinidrus/EpisAlpha.git && cd EpisAlpha

# 1. Credentials: .env is git-ignored and never committed. These variable NAMES are what
#    config/demo.toml references (ENV:...); put the values in yourself.
cat > .env <<'EOF'
openrouter_api_key=
alpha_vantage_api_key=
EOF
chmod 600 .env

# 2. Your ids, so files written into the repository stay yours.
export EPISALPHA_UID=$(id -u) EPISALPHA_GID=$(id -g)

# 3. Build, then run the quality gate in the container. The first start syncs the venv from
#    uv.lock into a named volume (about 2 minutes); later starts are instant.
docker compose build
docker compose run --rm check          # four checks + diagnose; expect 606 passed

# 4. Use it.
docker compose up -d phoenix ui         # Phoenix http://127.0.0.1:6006, workbench http://127.0.0.1:8501
docker compose run --rm cli demo seed
docker compose run --rm cli research run --case supported      # a [FIXTURE] fake run
docker compose run --rm cli replay <run_id>
docker compose run --rm cli export obsidian --run <run_id>     # open .episalpha/exports/vault in Obsidian
```

**Phoenix traces.** To send traces to Phoenix, uncomment `otlp_endpoint` under
`[observability]` in `config/demo.toml`. Without it, spans still go to
`.episalpha/logs/spans.jsonl`.

### How the orchestration is put together

| File | Role |
|---|---|
| `Dockerfile` | App toolbox image: pinned `python:3.12-slim` (same digest as the worker), git, the Docker CLI (from a pinned `docker:29.1.3-cli`), `uv 0.11.6`. Its build context is only `container/app-entrypoint.sh` (see `.dockerignore`), so `.env` and the data can never enter the image. |
| `container/app-entrypoint.sh` | Runs `uv sync --frozen --all-groups` into `/opt/venv` (a named volume), then the command. |
| `compose.yaml` | `ui` (Streamlit), plus tools-profile services `cli`, `check` and `setup-worker`. Phoenix comes in through `include: observability/compose.yaml`. No Docker socket. |
| `compose.live.yaml` | An overlay that adds the host's Docker socket to `ui`, `cli` and `setup-worker`, for live runs and the worker build only. |
| `scripts/setup_worker.py` | Clones Hermes at the pin, then builds the worker image with the M3-T04 recipe. `--record` writes the new image ID to the lock; `--local-venv` builds the local-launcher venv. |

Three design choices to keep:
- **The repository is mounted at the same absolute path inside the container as on the host.**
  The sandboxed worker's bind mounts are resolved by the host's Docker daemon, so the paths must
  agree. Always run `docker compose` from the repository root.
- **`network_mode: host`.** Every binding stays exactly as on the host:
  - Streamlit on `127.0.0.1:8501` (M5 article 9);
  - Phoenix at `127.0.0.1:6006` (the settings accept a loopback endpoint only);
  - the relay and the tool server on the `docker0` gateway for the worker.
- **Dependencies change → rebuild nothing.** The entrypoint re-syncs from `uv.lock` at every
  start. Rebuild the image only when the `Dockerfile` changes.

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

```bash
export DOCKER_GID=$(stat -c %g /var/run/docker.sock)
LIVE="docker compose -f compose.yaml -f compose.live.yaml"

$LIVE run --rm setup-worker                                   # clone Hermes c1488ac, build the worker
$LIVE run --rm setup-worker python scripts/setup_worker.py --record   # on a new machine (see below)
$LIVE up -d ui
$LIVE run --rm cli research run --case supported --runtime hermes      # needs ingested filings, see 5.1
```

**Expect a new worker image ID.** Docker builds are not bit-for-bit reproducible.
- The lock (`config/runtime.lock.json` → `hermes.worker_image.id`) holds the ID built on the old
  machine.
- On this machine, the rebuild inside the container matched the lock
  (`sha256:6d1ed1ee…54cd`), but only because the build cache was warm.
- A fresh machine will print `differs from the lock`. Run it again with `--record`, review the
  lock diff, and re-run the G3 live checks before trusting it:

```bash
$LIVE run --rm setup-worker python scripts/setup_worker.py --local-venv   # local-launcher tests
$LIVE run --rm --entrypoint episalpha-entrypoint cli \
    pytest -q -m live tests/integration/test_runtime_boundary.py tests/integration/test_hermes_runtime.py
```

**Verified and not verified.** From inside the app container, these steps are verified:
- socket access (`client 29.1.3 server 29.1.3`);
- the worker build;
- a fresh clone at the pin.

**A live research run from inside the container has not been executed yet.** The G3 live
evidence comes from host-side runs.

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
