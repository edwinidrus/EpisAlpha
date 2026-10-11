# M3-T04 journal

## Attempt 1 — 2026-10-11 06:20–06:35 UTC — claude-opus-5-5
- Owner decisions (2026-10-10): digest-pinned Docker pulls allowed. **Host engine:** harden the
  current rootful Docker; rootless or userns-remap stays an owner TODO, so a container escape
  would still land as root in the WSL distro.
- Verify:
  - `docker version` -> 29.1.3 (rootful), default seccomp; `docker compose version` -> 2.40.3;
    no `docker buildx`.
  - Upstream image at the pin: Docker Hub `nousresearch/hermes-agent` has rolling tags (`v0.21.6`,
    `v2026.9.21`, rc builds) but nothing tagged 0.21.3/c1488ac. The upstream Dockerfile at the
    pin installs ffmpeg, node, playwright, docker-cli, ssh and an s6 init, which is far more
    attack surface than a stage worker needs. **Decision:** a minimal image from
    `python@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258`
    (python:3.12-slim-bookworm). Hermes is installed from a `git archive` of c1488ac with
    upstream's own `uv.lock` (`uv sync --frozen --no-dev --extra mcp`, uv 0.11.6), plus the
    worker and the forwarder. Built ID
    `sha256:6d1ed1ee5e6a18542d8ad64ac087930e5e5843a69a7a69d046485f45412854cd` (797 MB),
    recorded in `config/runtime.lock.json` -> `hermes.worker_image`.
  - **Network finding.** A plain `--internal` network still gives the host an address on the
    bridge (172.31.250.1). From a container on it, a host service bound to that address or to
    `0.0.0.0` was reachable (`CONNECTED b'hello\n'`). This host has wildcard listeners on 8000
    and 8080. With `-o com.docker.network.bridge.inhibit_ipv4=true` the host has no address
    there: `172.31.251.1:8000 -> ConnectionRefusedError`, `172.17.0.1:8000 -> Network is
    unreachable`.
  - Design: the worker sits on `episalpha-worker` (internal, no host address, 172.31.252.0/24,
    `--dns 127.0.0.1`). A forwarder container (same image, hardened) on `bridge` plus the
    worker network at 172.31.252.2 forwards 8080 to the relay and 8081 to the stage's MCP
    server, both bound by the host on docker0 (172.17.0.1). The relay token and the MCP token
    still gate both.
  - Baseline: four checks green, 497 passed.
  - Red first: `tests/runtime/test_sandbox.py` was written after `sandbox.py` (the first draft
    of `sandbox.py` came out of the design probes). The boundary test was written before the
    image existed.
- Did:
  - `src/episalpha/runtime/sandbox.py`: `SandboxConfig` (refuses an unpinned image),
    `network_create_command`, `forwarder_command`, `worker_command`, `SandboxLauncher`
    (network, forwarder, hardened `docker run`, watchdog `docker stop -t 2` then `kill`,
    measured stop time, cancel), `build_image` (minimal context: no repository, no `.env`).
  - `container/Dockerfile`, `container/forwarder.py`. The pack named `runtime/`; renamed
    `container/` because a top-level `runtime/` would merge into the tests' `runtime`
    namespace package.
  - No `compose.yaml`: the launcher issues the equivalent `docker` commands, and the offline
    tests pin them. One source of truth.
  - `src/episalpha/runtime/hermes.py`: the `WorkerLauncher` protocol, with `LocalLauncher`
    (venv) and the sandbox. The spec is mounted read-only; output goes to a per-stage
    directory (mode 0777, since the worker's uid 10001 has no host account).
  - `worker/hermes_stage.py`: reports its own `HERMES_HOME` files and `state.db` rows (in the
    container that home is a tmpfs the host cannot see).
  - Tests: `tests/runtime/test_sandbox.py` (7, offline),
    `tests/integration/test_runtime_boundary.py` (3, live, no model calls),
    `tests/integration/test_hermes_runtime.py::test_three_live_stages_in_the_container` (live).
    Adapter and live tests moved to the launcher API.
- Ran: `uv run pytest -q -s -m live tests/integration/test_runtime_boundary.py` -> `3 passed`.
  Probe verdicts from inside the worker:
  - `see_repository`: BLOCKED FileNotFoundError; `open_canonical_db`: BLOCKED
    FileNotFoundError; `read_env_file`: BLOCKED FileNotFoundError
  - `write_spec`: BLOCKED PermissionError; `write_root_filesystem`: BLOCKED `[Errno 30]
    Read-only file system`; `write_skills_mount`: BLOCKED `[Errno 30] Read-only file system`
  - `https_example_com`: BLOCKED `Temporary failure in name resolution`; `dns_example_com`:
    BLOCKED gaierror
  - `list_mnt_c`, `list_host_home`, `docker_socket`: BLOCKED FileNotFoundError
  - `tcp_172.31.252.1_8000` and `_8080`: BLOCKED ConnectionRefusedError; `tcp_172.17.0.1_8000`,
    `tcp_172.17.0.1_<relay port>`, `tcp_1.1.1.1_443`: BLOCKED `Network is unreachable`;
    `tcp_172.31.252.2_9999`: BLOCKED ConnectionRefusedError
  - `relay_via_forwarder`: **ALLOWED** `b'relay-ok'` (the only allowed path)
  - `fork_400_processes`: BLOCKED `BlockingIOError: [Errno 11] Resource temporarily
    unavailable` (pids limit 128)
  - `fill_tmp_200_mib`: BLOCKED `[Errno 28] No space left on device` (64 MiB tmpfs)
  - `uid`: 10001. A symlink planted at `out/result.json` -> `/etc/hostname` is refused by the
    host reader (`OSError`, `O_NOFOLLOW`).
  - **Cancel:** `stop_seconds=2.57`, total 6.62 s (cancel issued at 3 s). **Timeout:**
    `stop_seconds=2.57`, total 7.43 s (deadline 3 s). No leftover worker or forwarder
    containers.
- **Real-provider run through the container** (2026-10-11T06:29:57Z):
  `test_three_live_stages_in_the_container` -> `1 passed in 109.90s`. Run `run.live-2604fb48`,
  trace `f8c7b412beee232c837192a897faff24` (21 spans in one trace in Phoenix), 6 requests, all
  `served_by` Nvidia, usage 23,357 prompt / 1,955 completion tokens, `cost_eur: None`.
  Researcher 3 requests (claims c1 -> `synthetic-span.revenue`, c2 -> `synthetic-span.demand`),
  critic 2, synthesizer 1 (stance `abstain`; all assertions cite run claims).
  `learning_writes: []` in every stage.
  - Observation: the worker's tmpfs home held `.cache/uv/...` entries, so Hermes invoked `uv`
    in the sandbox (likely a lazy-dependency check). With no network nothing installed; noted
    for the owner.
- Four checks: All checks passed; 64 files formatted; no issues in 32 source files; `504
  passed, 8 deselected`.
- Live requests this task: 6. Session total about 28 of 40.
- Outcome: PASS. The host-engine hardening (rootless or userns-remap) remains an owner action.
