# M3-T04 — Whole-worker isolation and watchdog

| Field | Value |
|---|---|
| Status | DONE |
| Depends on | M3-T03 |
| Phase constitution | [../CONSTITUTION.md](../CONSTITUTION.md) (inherits [global](../../CONSTITUTION.md)) |
| Plan source | plan §9 M3-T04 card, §4.2 (Docker image, A5), §14 rows A09 and A10, cancellation target |
| Journal | `tasks/M3-T04-isolation.journal.md` |

## 0. Context to load

Load these and nothing else:
- `implementation/CONSTITUTION.md`
- `implementation/M3-runtime/CONSTITUTION.md`, articles 6–8 and 11
- `src/episalpha/runtime/hermes.py`, `model_relay.py` and `port.py`
- `config/runtime.lock.json`, the `hermes` pin
- The plan §14 rows A09 and A10, and the cancellation target: the parent and children stop
  within 10 s.

## 1. Plan

- **Goal:** the entire Hermes worker runs in a container that can see only its frozen inputs and
  the relay. Timeout and cancellation kill it, with its children, within 10 s, and leave partial
  output marked incomplete.
- **Files:**
  - `src/episalpha/runtime/sandbox.py`
  - `runtime/Dockerfile`, based on upstream's Hermes image at the pinned commit
  - `runtime/compose.yaml`
  - Focused test: `tests/integration/test_runtime_boundary.py` (`live`, because it needs
    Docker). A fake provider is fine here.
- **Produces:** `class SandboxedWorker`, with `start(run_id, snapshot_dir, harness_dir, out_dir) -> handle`,
  `wait(handle, deadline)` and `cancel(handle)`.
  - Mounts: the snapshot RO, the harness RO, the promoted skills RO (A13; empty in v0.1), and
    `out/<run_id>` RW.
  - **Hardening (A12):**
    - image pinned **by digest**, not by tag;
    - non-root user;
    - `cap_drop: [ALL]` and `security_opt: [no-new-privileges:true]`;
    - `read_only: true` root filesystem, with size-capped tmpfs for `/tmp` and `HERMES_HOME`;
    - `pids_limit`, memory and CPU limits;
    - the default seccomp profile;
    - `dns` configured so external names do not resolve (the CVE-2024-29018 class).
  - **Host engine (owner decision, recorded in the journal).**
    - The engine seen on 2026-10-10 is rootful Docker Engine 29.1.3 inside WSL Ubuntu 24.04,
      with only the default seccomp profile. A container escape would land as root in the
      distro that holds `.env`, the repository and `/mnt/c`.
    - Recommended: run the worker under **rootless Docker** or `userns-remap`.
    - Optional: the gVisor `runsc` runtime, if it installs on WSL2.
    - Keep the engine patched, and record its version.
  - It never mounts the repository, `.episalpha/app.sqlite3`, the labels path, the Docker
    socket or `.env`.
  - Networks: the worker sits on an internal network whose only reachable endpoint is the relay
    service. The relay has separate egress to the provider host.
  - Watchdog: wall-time deadline from `limits.run_wall_time_seconds`, enforced by the parent.
    `docker stop -t` is followed by `kill`. The time to stop is measured.
  - Partial output stays in `out/<run_id>` and is reported as incomplete, never complete.
- **Out of scope:**
  - Kubernetes.
  - Secrets platforms.
  - Alternate sandbox backends.
  - The runner job lifecycle (M4-T01).
- **Do not:**
  - Pass the provider key into the container environment.
  - Use `--privileged` or `network_mode: host`.

## 2. Verify (before building)

- [ ] `docker version` and `docker compose version` work on this WSL host. If not: **BLOCKED**
      on the live test. Offline unit tests of `sandbox.py` command construction can still pass;
      report them as such.
- [ ] The upstream image reference for `c1488ac` exists (`docker manifest inspect` or a pull).
      Journal the digest.
- [ ] Baseline: the four checks and `diagnose.py` are green.
- [ ] **Red first.** Offline unit tests assert that the generated docker/compose arguments
      contain the RO mounts and no forbidden mounts or environment. The live boundary tests are
      written before the Dockerfile.

## 3. Build

1. Write the Dockerfile from the pinned upstream image. Add only the EpisAlpha MCP server entry
   and the harness mount point.
2. Write `compose.yaml` with two services (worker, relay), the internal network, and the mounts.
3. Write `sandbox.py`: start, wait, cancel, measuring time, and emitting `stage.transition` and
   `run.terminal`-style events with `duration_ms` and `exit_code`.
4. Write the live boundary tests. Inside the worker, each of these must fail:
   - read the labels path;
   - open the canonical DB;
   - write to the snapshot;
   - `curl https://example.com`;
   - resolve an external name (`getent hosts example.com`), so DNS exfiltration is blocked;
   - list `/mnt/c` or the host home directory;
   - connect to any host-gateway port other than the relay;
   - write to the promoted-skills mount;
   - a fork bomb is contained by `pids_limit`, and disk fill is contained by the tmpfs cap;
   - a symlink planted in `out/<run_id>` pointing at a host path is **not followed** by the
     host reader.
   Then cancel a sleeping worker and assert it stops in under 10 s, with no orphan processes.

## 4. Test

```bash
uv run pytest -q tests/runtime
uv run pytest -q -m live tests/integration/test_runtime_boundary.py
uv run ruff check . && uv run ruff format --check . && uv run mypy src/episalpha && uv run pytest -q -m "not live"
```

Acceptance:
- [ ] The worker cannot change evidence or harness, or read hidden labels.
- [ ] No Docker socket is mounted.
- [ ] An unrelated outbound connection fails.
- [ ] Timeout and cancel terminate child processes, with the measured time recorded.
- [ ] Partial output is retained but never marked complete.
- [ ] External DNS does not resolve. `/mnt/c` and the host home are invisible. Only the relay
      port is reachable. The skills mount is read-only. A planted symlink is not followed.
      Fork bomb and disk fill are contained.
- [ ] The image is pinned by digest. The host-engine decision (rootless, userns-remap or gVisor)
      is recorded.

## 5. Diagnose

- [ ] `diagnose.py`: no regression.
- [ ] The journal has the image digest, the measured cancel time, and the output of each
      forbidden-access attempt (the shortest decisive line).
- [ ] Run G3 in full, including one real-provider run through the container. Append the result
      to `../GATE.md`.

## 6. Stop and hand off

- **BLOCKED if:**
  - Docker is unavailable;
  - the upstream image is unavailable at the pin;
  - the network isolation cannot be proven.
- **Record:** M3 `PROGRESS.md`, `STATUS.md`, the journal, and G3.
- **Next:** M4-T01.
