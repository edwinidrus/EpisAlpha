# Portable Docker orchestration — design

| Field | Value |
|---|---|
| Date | 2026-10-11 |
| Status | Draft for owner review |
| Owner decisions | Run everywhere including live Hermes runs; distribute by `git clone` + local build; approach A (Docker-native) — all three on 2026-10-11 |
| Amendment | A15 (to be recorded in `docs/implementation/progress.md` on approval) |
| Delivery | Two task cards: T1 portable offline stack, T2 `compose` sandbox topology + live check |

## 1. Intent

**Outcome.** EpisAlpha runs from `git clone` + `docker compose build` on any machine with Docker
Engine ≥ 26: Linux (amd64/arm64, including a server or VM), macOS on Intel or Apple Silicon and
Windows (Docker Desktop, WSL2 backend). This covers the full stack: UI, CLI, quality gate,
Phoenix, fake runs, Obsidian export **and live Hermes research runs**. The same `docker compose`
commands work unchanged on every OS.

**Constraints.**
- Every M3 isolation property of the research worker holds in every topology (§4.3).
- Running on a Linux host with `uv run` (no containers) keeps working as today.
- Phoenix stays reachable from the host's loopback only; the settings' loopback-only
  `otlp_endpoint` rule is not relaxed.
- No registry, no image publishing, no CI (owner decision). Images build natively per machine.
- Minimal dependencies: no new Python packages.

**Success criteria.**
1. On this Linux host: build, `check` (606+ passed), `up`, a fake run, an export visible on the
   host, a compose-topology isolation probe, and **one owner-approved live run**, all recorded
   with real output.
2. On macOS (Apple Silicon) and Windows (Docker Desktop): the owner runs the same sequence. This
   is a manual owner check; it is not claimed done until recorded.

**Out of scope.** Registry/CI publishing; Kubernetes; rootless Docker or userns-remap (stays the
G3 owner TODO); changing the research runtime, harness or model route; Docker Desktop's
experimental host networking.

## 2. Why today's setup is Linux-only

| Piece | Today | Breaks on |
|---|---|---|
| App containers | `network_mode: host` | Docker Desktop (host networking differs) |
| Repository mount | `${PWD}:${PWD}`, the same absolute path inside and out | Windows paths (`C:\…`) |
| App image | Toolbox: code bind-mounted, `uv sync` at every start | Any machine without the checkout mounted |
| Worker → relay | Relay and MCP server bind the `docker0` gateway `172.17.0.1`; the forwarder targets it | Docker Desktop has no `docker0` gateway |
| Worker files | Bind mounts of host paths, resolved by the host daemon | Anything where the app's paths are not host paths |

## 3. Layout and images (T1)

```text
host: 127.0.0.1:8501 (UI)   127.0.0.1:6006 (Phoenix)          <- the only published ports
          |                        |
   +------+--- "net" (network anchor: owns the ports and the shared localhost) -----+
   |  ui (Streamlit)    cli / check (one-off)    phoenix                             |
   |      `-- relay + MCP tool server (live runs) listen in this namespace           |
   +-------------------------- network: episalpha-app (private bridge) --------------+
                                       |
                    forwarder (joins episalpha-app + episalpha-worker)
                                       |
                    worker (episalpha-worker: internal, no host address, no DNS)
```

### 3.1 App image

- Multi-stage `Dockerfile`. A build stage runs `uv sync --frozen --no-dev` against `uv.lock`
  into `/opt/venv`; the final stage copies the venv plus `src/`, `apps/`, `harnesses/`,
  `eval_cases/`, `scripts/`, `worker/`, `container/`, `config/*.example.toml`,
  `config/runtime.lock.json` and `pyproject.toml` to `/app`.
- Base images stay pinned by digest. Verified 2026-10-11: the pinned `python`, `docker` CLI and
  Phoenix digests are multi-arch indexes that include `linux/arm64`.
- `.dockerignore` excludes `.env`, `.episalpha/`, `.venv/`, `.git/`, caches and `tests/`.
  Neither the data, the credentials nor the test suite enter the image.
- The image runs as a non-root user. The uid/gid default to 1000 and are set by the compose
  variables `EPISALPHA_UID` / `EPISALPHA_GID` (on Linux, your own ids keep bind-mounted files
  yours; Docker Desktop maps ownership itself).

### 3.2 Network anchor

- A service `net` built from the same app image, running an idle stdlib command (no new image).
- `ui`, `cli`, `setup-worker`, `phoenix` (and `check` in the dev override) use `network_mode: service:net`, so they
  share one network namespace and one `127.0.0.1`.
- `net` joins the private bridge `episalpha-app` (explicit `name:`, so the sandbox can refer to
  it) and publishes only `127.0.0.1:8501:8501` and `127.0.0.1:6006:6006`.
- Phoenix leaves its separate `episalpha-phoenix` network; from the host it is still reachable
  on `127.0.0.1:6006` only. The settings rule (`otlp_endpoint` must be loopback) is unchanged.
- Docker delivers a published port to the anchor's address on `episalpha-app`, not to its
  `127.0.0.1`. The `ui` command therefore sets `--server.address 0.0.0.0` inside the namespace,
  and Phoenix already binds `0.0.0.0` inside its container. Host exposure stays loopback-only
  through the `127.0.0.1:` port mappings; on the private network only `episalpha-app` members
  (the forwarder) could reach them, never the worker. `.streamlit/config.toml` keeps
  `127.0.0.1` for a non-container `uv run`. M5 constitution article 9 ("Streamlit binds to
  127.0.0.1") is reworded under A15 to "reachable from the host's loopback only".

### 3.3 Mounts (relative paths only)

| Host | Container | Mode |
|---|---|---|
| `./.episalpha` | `/app/.episalpha` | read-write (data root; the Obsidian vault stays browsable on the host) |
| `./config` | `/app/config` | read-only (the owner's `demo.toml`) |
| `.env` | environment | `env_file`, `required: false` |

`${PWD}` and the same-absolute-path mount are removed. `working_dir` is `/app`.

### 3.4 Development override

`compose.dev.yaml` bind-mounts the whole repository at `/app` (the image's venv stays in place)
so `check` and the CLI run the working copy:

```bash
docker compose -f compose.yaml -f compose.dev.yaml run --rm check
```

The `check` service is defined only in `compose.dev.yaml`, because the test suite is not in
the image. `compose.yaml` keeps `ui`, `cli`, `setup-worker`, `net` and `phoenix`.

### 3.5 Windows safety

`.gitattributes` forces LF line endings for `*.sh`, `Dockerfile*` and `container/*`, so the
entrypoint still runs after a Windows clone with `core.autocrlf=true`.

## 4. Live sandbox: the `compose` topology (T2)

### 4.1 Selection

`SandboxConfig` gains `topology: Literal["host", "compose"] = "host"`. `compose.yaml` sets
`EPISALPHA_SANDBOX_TOPOLOGY=compose`. Without that variable everything behaves exactly as today.
In `compose` mode the network names, the anchor's name and the stage volume name are fixed
constants mirrored by `compose.yaml` (`episalpha-app`, `net`, `episalpha-stages`). They are not
new settings keys.

### 4.2 What differs

| | `host` (today, Linux) | `compose` (new, every OS) |
|---|---|---|
| Relay + MCP listen on | the `docker0` gateway `172.17.0.1` | `0.0.0.0` inside the shared namespace; on the network only `episalpha-app` members can reach it; ports are random and never published; the relay token is required as today |
| Forwarder starts on → targets | default bridge → `172.17.0.1:<port>` | `episalpha-app` → `net:<port>` |
| Stage work dir | `<data_root>/work/<run>/<stage>/` | `/stages/<run>/<stage>/` on the named volume `episalpha-stages`, mounted in the app containers |
| Worker sees | bind of `spec.json` (ro) + `out/` (rw) | `--mount type=volume,src=episalpha-stages,volume-subpath=<run>/<stage>/in,readonly` and `…/out` (rw) |
| Output read | from the host path, without following symlinks | from `/stages/…`, without following symlinks (same code) |

The stage layout in `compose` mode is `in/spec.json` + `out/`. The app writes `in/` with mode
0644 and sets `out/` to 0777, as `hermes.py` does today (the worker runs as uid 10001). Probe on
this host (2026-10-11, Engine 29.1.3, API 1.52): a sub-path mount exposed only its own directory;
a sibling file in the same volume was not reachable.

### 4.3 Unchanged in both topologies (the M3 guarantees)

- The worker network is `--internal` with `inhibit_ipv4`: the host has no address on it.
- The forwarder is the worker's only neighbour and forwards exactly two fixed ports; it takes
  no routing input from the worker.
- `--dns 127.0.0.1`; read-only rootfs; `cap-drop ALL`; `no-new-privileges`; non-root uid 10001;
  pids, memory and CPU limits; size-capped tmpfs; image pinned by content ID or digest.
- The provider key lives only in the relay. The worker never mounts the data root, the canonical
  database, labels, `.env` or the Docker socket.
- The watchdog (`docker stop` then `docker kill`) and cancellation are unchanged.

**Trust shift, recorded.** In `compose` mode the forwarder sits on `episalpha-app` instead of
the default bridge, so it could reach the UI and Phoenix ports in the anchor's namespace.
Because it takes no routing input from the worker, this gives the worker no new path. Today it
can reach the host's gateway services instead.

### 4.4 Docker socket

It stays in `compose.live.yaml` only, mounted for `ui`, `cli` and `setup-worker`, never for the
worker. Its group comes from the compose variable `DOCKER_GID`: on Linux, the socket's group (`stat
-c %g /var/run/docker.sock`); on Docker Desktop, `0`. The Desktop value is unverified until the
owner check.

### 4.5 Worker image

`setup-worker` is unchanged. `build_image` uploads a minimal context through the socket, so it
works from inside a container on any OS. The worker image ID in `config/runtime.lock.json` is
per machine and per architecture: each new machine runs `setup-worker --record` (existing
HANDOFF procedure). Whether Hermes' pinned dependencies install on `linux/arm64` is unverified
until the owner's Apple Silicon check.

## 5. Error handling

- `compose` mode without the stage volume, or without `episalpha-app`, gives a clear refusal
  before admission (extending the existing Hermes readiness check), never a queued run stuck
  holding the job slot.
- Docker Engine older than API 1.45 (no `volume-subpath`) gives a readiness refusal naming the
  minimum version.
- Phoenix down never fails a run (unchanged); spans still go to `spans.jsonl`.

## 6. Testing and verification

**Automated (default offline suite):**
- `compose`-topology command builders: forwarder network and target, worker mounts are volume
  sub-paths only (no `type=bind`, never the data root or the socket), and the hardening flags are
  identical to `host`.
- Topology selection from `EPISALPHA_SANDBOX_TOPOLOGY`; invalid values are refused.
- Readiness refusals (§5).
- Existing `host` tests stay green, unmodified.

**Real Docker on this Linux host (recorded output):**
1. `docker compose build`; `docker compose -f compose.yaml -f compose.dev.yaml run --rm check`:
   four checks and diagnose (606+ passed).
2. `docker compose up -d`: the UI's `/_stcore/health` is `ok` on `127.0.0.1:8501`; Phoenix
   answers on `127.0.0.1:6006` and receives a trace; `ss -ltn` shows only loopback bindings
   for those ports.
3. `docker compose run --rm cli demo seed`, a fake `research run`, `export obsidian`: the vault
   appears under `./.episalpha/exports/vault` on the host.
4. Compose-topology isolation probe, no model calls: a probe worker reaches the forwarder's two
   ports; any other address and DNS fail; only its stage sub-path is visible.
5. **One live Hermes run** (`--runtime hermes`) in the compose topology. The owner is asked for
   approval immediately before it (about 8 model requests).

**Owner checks (manual, recorded with date and versions):** on macOS Apple Silicon and Windows
Docker Desktop, run steps 1–5, including `setup-worker --record` and the `DOCKER_GID=0` socket
access.

## 7. Documentation and governance

- HANDOFF §3–4 and the README Docker block are rewritten with OS-neutral commands. Only the Linux
  socket-group lookup is shell-specific, and it is optional.
- Amendment A15 in `docs/implementation/progress.md`. Within it: the M3 constitution and
  `sandbox.py` docstring wording on `docker0` is updated to describe both topologies, and M5
  constitution article 9 is reworded as in §3.2.
- Two task packs (`T1`, `T2`) with STATUS rows; each follows Plan → Verify → Build → Test →
  Diagnose. T2 depends on T1. Commits remain an owner action.
