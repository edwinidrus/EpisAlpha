# M3-T05 journal

## Attempt 1 — 2026-10-11 — OpenCode openai/gpt-6.1-sol

**Result:** DONE on Linux, per controller ruling. No completed live thesis in compose
yet; macOS/Windows owner checks pending; rootless Docker / userns-remap remains an
owner TODO. The supported case abstained because the real filings are not ingested
(G2 owner checkpoint). Synthesizer provider failure is `FAILED` / `SOURCE_FAILED`,
not an abstention or completed thesis.

### Preconditions and scope

- Initial Task 6 stopped NEEDS_CONTEXT: the supposed stub pack and M3 docker0 replacement
  target were absent. Controller Answer 1 authorized creating the pack from TASK.md and
  adding exactly one sub-bullet to article 8; M5 article 9 keeps its bold label.
- Tasks 4–5 implementation/tests were already committed; the live run was already done
  by the controller with owner approval. This task changed records only, skipped Steps
  2–3 entirely, and did not run any live model command or boundary probe.
- Quotes below come from `task-4-report.md`, `task-5-report.md` (**Answer 1 /
  continuation**) and `live-run-evidence.md` in the controller's A15 workspace. They are
  earlier same-day evidence, not commands executed by this Task 6 implementer.

### Task 4 — compose sandbox implementation (quoted outputs)

Commit `f8b1d78437122072c1a15c063a30f72ce0f399ae`:
`M3-T05: compose sandbox topology (forwarder by name, stage volume sub-paths, preflight)`.

`uv run pytest -q tests/runtime/test_sandbox.py` RED (exit 2), decisive lines:

```text
E   ImportError: cannot import name 'COMPOSE_STAGE_ROOT' from 'episalpha.runtime.sandbox' (/home/edharth/hobbys/EpisAlpha/src/episalpha/runtime/sandbox.py)
ERROR tests/runtime/test_sandbox.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.06s
```

Same focused command GREEN (exit 0): `16 passed in 1.02s`.
Four checks (exit 0):

```text
All checks passed!
82 files already formatted
Success: no issues found in 38 source files
628 passed, 8 deselected in 15.73s
```

Corrected preservation self-check (exit 0; the first check-script attempt failed with
`AssertionError: Watchdog`, not a repository failure):

```text
Preservation checks passed: hardening flags, worker network, hardening bullets, all existing test/helper bodies; exactly 9 new tests.
```

### Task 5 — readiness, runtime wiring and boundary probes (quoted outputs)

Commit `1296edd23b84c94b55afd71b94d6db063b63d4d2`:
`M3-T05: wire the compose topology into readiness and the runtime; probe both topologies`.

Mount-guard RED, `uv run pytest -q tests/runtime/test_sandbox.py -k volume_root_and_parent_traversal_mounts`:

```text
E               Failed: DID NOT RAISE <class 'ValueError'>
FAILED tests/runtime/test_sandbox.py::test_compose_refuses_volume_root_and_parent_traversal_mounts
1 failed, 16 deselected in 0.03s
```

Focused sandbox GREEN: `17 passed in 1.02s`.
Readiness RED, `uv run pytest -q tests/runtime/test_sandbox_services.py`:

```text
E       Failed: DID NOT RAISE <class 'episalpha.contracts.errors.EpisAlphaError'>
FAILED tests/runtime/test_sandbox_services.py::test_compose_without_the_socket_is_refused_before_admission
FAILED tests/runtime/test_sandbox_services.py::test_an_unknown_topology_is_refused_cleanly
2 failed, 1 passed in 0.10s
```

Readiness GREEN: `3 passed in 0.10s`.
Task 5 recorded local worker image:
`sha256:c75ad359ae99582f83f18e0473ee7f3b9e040ffa1e7afbf7097fc0b1b325484d`.

Initial compose probe stopped on `E       AssertionError: {'list_host_home', 'relay_via_forwarder'}`
and `1 failed, 2 passed in 12.16s`. Controller Answer 1 fixed the input collision
(app HOME `/tmp`, worker writable `/tmp`): use actual host home and also probe `/stages`.
The allowed-set assertion, uid, symlink and hardening checks were not weakened.
The accepted continuation verdicts are quoted below (same code, today; no Task 6 rerun).

Host (Task 5, exit 0): `uv run pytest -q -m live tests/integration/test_runtime_boundary.py -s`

```text
{
 "see_repository": "BLOCKED: FileNotFoundError: [Errno 2] No such file or directory: '/home/edharth/hobbys/EpisAlpha'",
 "open_canonical_db": "BLOCKED: FileNotFoundError: [Errno 2] No such file or directory: '/home/edharth/hobbys/EpisAlpha/.episalpha/app.sqlite",
 "read_env_file": "BLOCKED: FileNotFoundError: [Errno 2] No such file or directory: '/home/edharth/hobbys/EpisAlpha/.env'",
 "write_spec": "BLOCKED: PermissionError: [Errno 13] Permission denied: '/run/episalpha/spec.json'",
 "write_root_filesystem": "BLOCKED: OSError: [Errno 30] Read-only file system: '/opt/hermes/planted'",
 "write_skills_mount": "BLOCKED: OSError: [Errno 30] Read-only file system: '/opt/skills/new-skill.md'",
 "https_example_com": "BLOCKED: URLError: <urlopen error [Errno -3] Temporary failure in name resolution>",
 "dns_example_com": "BLOCKED: gaierror: [Errno -3] Temporary failure in name resolution",
 "list_mnt_c": "BLOCKED: FileNotFoundError: [Errno 2] No such file or directory: '/mnt/c'",
 "list_host_home": "BLOCKED: FileNotFoundError: [Errno 2] No such file or directory: '/home/edharth'",
 "list_stage_volume_root": "BLOCKED: FileNotFoundError: [Errno 2] No such file or directory: '/stages'",
 "docker_socket": "BLOCKED: FileNotFoundError: [Errno 2] No such file or directory: '/var/run/docker.sock'",
 "tcp_172.31.252.1_8000": "BLOCKED: ConnectionRefusedError: [Errno 111] Connection refused",
 "tcp_172.31.252.1_8080": "BLOCKED: ConnectionRefusedError: [Errno 111] Connection refused",
 "tcp_172.17.0.1_8000": "BLOCKED: OSError: [Errno 101] Network is unreachable",
 "tcp_172.17.0.1_43023": "BLOCKED: OSError: [Errno 101] Network is unreachable",
 "tcp_172.31.252.2_9999": "BLOCKED: ConnectionRefusedError: [Errno 111] Connection refused",
 "tcp_1.1.1.1_443": "BLOCKED: OSError: [Errno 101] Network is unreachable",
 "relay_via_forwarder": "ALLOWED: b'relay-ok'",
 "fork_400_processes": "BLOCKED: BlockingIOError: [Errno 11] Resource temporarily unavailable",
 "fill_tmp_200_mib": "BLOCKED: OSError: [Errno 28] No space left on device",
 "uid": 10001
}
.cancel: stop_seconds=2.09 total=5.26
.timeout: stop_seconds=2.14 total=5.43
.
3 passed in 12.03s
```

Compose (Task 5, exit 0):

```bash
export DOCKER_GID=$(stat -c %g /var/run/docker.sock) EPISALPHA_PHOENIX_PORT=6007
docker compose -f compose.yaml -f compose.dev.yaml -f compose.live.yaml run --rm -e EPISALPHA_PROBE_HOST_HOME="$HOME" --entrypoint pytest cli -q -m live tests/integration/test_runtime_boundary.py -s
```

```text
{
 "see_repository": "BLOCKED: FileNotFoundError: [Errno 2] No such file or directory: '/app'",
 "open_canonical_db": "BLOCKED: FileNotFoundError: [Errno 2] No such file or directory: '/app/.episalpha/app.sqlite3'",
 "read_env_file": "BLOCKED: FileNotFoundError: [Errno 2] No such file or directory: '/app/.env'",
 "write_spec": "BLOCKED: PermissionError: [Errno 13] Permission denied: '/run/episalpha/spec.json'",
 "write_root_filesystem": "BLOCKED: OSError: [Errno 30] Read-only file system: '/opt/hermes/planted'",
 "write_skills_mount": "BLOCKED: FileNotFoundError: [Errno 2] No such file or directory: '/opt/skills/new-skill.md'",
 "https_example_com": "BLOCKED: URLError: <urlopen error [Errno -3] Temporary failure in name resolution>",
 "dns_example_com": "BLOCKED: gaierror: [Errno -3] Temporary failure in name resolution",
 "list_mnt_c": "BLOCKED: FileNotFoundError: [Errno 2] No such file or directory: '/mnt/c'",
 "list_host_home": "BLOCKED: FileNotFoundError: [Errno 2] No such file or directory: '/home/edharth'",
 "list_stage_volume_root": "BLOCKED: FileNotFoundError: [Errno 2] No such file or directory: '/stages'",
 "docker_socket": "BLOCKED: FileNotFoundError: [Errno 2] No such file or directory: '/var/run/docker.sock'",
 "tcp_172.31.252.1_8000": "BLOCKED: ConnectionRefusedError: [Errno 111] Connection refused",
 "tcp_172.31.252.1_8080": "BLOCKED: ConnectionRefusedError: [Errno 111] Connection refused",
 "tcp_172.17.0.1_8000": "BLOCKED: OSError: [Errno 101] Network is unreachable",
 "tcp_172.17.0.1_42047": "BLOCKED: OSError: [Errno 101] Network is unreachable",
 "tcp_172.31.252.2_9999": "BLOCKED: ConnectionRefusedError: [Errno 111] Connection refused",
 "tcp_1.1.1.1_443": "BLOCKED: OSError: [Errno 101] Network is unreachable",
 "relay_via_forwarder": "ALLOWED: b'relay-ok'",
 "fork_400_processes": "BLOCKED: BlockingIOError: [Errno 11] Resource temporarily unavailable",
 "fill_tmp_200_mib": "BLOCKED: OSError: [Errno 28] No space left on device",
 "uid": 10001
}
.cancel: stop_seconds=2.1 total=5.28
.timeout: stop_seconds=2.13 total=5.4
.
3 passed in 12.19s
```

Task 5 final four checks (exit 0):

```text
All checks passed!
83 files already formatted
Success: no issues found in 38 source files
632 passed, 8 deselected in 16.10s
```

### Controller live evidence (verbatim; not executed here)

```text
# Task 6 live-run evidence (executed by the controller, owner-approved, 2026-10-11)

Environment: Linux host, Docker Engine 29.1.3 (API 1.52), Compose v5.0.1; compose topology;
EPISALPHA_PHOENIX_PORT=6007 (host 6006 used by another project); otlp_endpoint unset (spans → JSONL only).

## Attempt A — approved command, stale image
`docker compose -f compose.yaml -f compose.live.yaml run --rm cli research run --case supported --runtime hermes`
-> exit 1, `OSError: [Errno 99] Cannot assign requested address` in the relay's server_bind.
Root cause: episalpha-app:local was built in Task 2, before Tasks 4–5; the baked code still bound
the docker0 gateway. No model request was made. The crash left run-64371faa7c96 QUEUED (holding
the single job slot). Fix: `docker compose -f compose.yaml -f compose.live.yaml build`; inside the
rebuilt image `sandbox_config` reports `compose 0.0.0.0 /stages`.

## Attempt B — recover the stranded run (same request)
`docker compose -f compose.yaml -f compose.live.yaml run --rm cli research recover run-64371faa7c96`
-> exit 5, state ABSTAINED, reason "essential evidence missing: no eligible documents at the research
cutoff. Next inquiry: ingest the filings for this instrument and cutoff.", usage model requests 0,
tool calls 0, trace 2fe7fdd04060962745f6a783257b9f26. (The case's real filings are not ingested on
this machine — G2 owner checkpoint.) The worker was never launched.

## Attempt C — owner re-approved: synthetic snapshot
`docker compose -f compose.yaml -f compose.live.yaml run --rm cli research run --snapshot snapshot.run-53a5b38d52ae --question "Did the company change full-year guidance, and what did it attribute the change to?" --runtime hermes`
-> exit 4, run-3e482d7c5938, state FAILED, reason "synthesizing: provider_failure: SOURCE_FAILED",
error_code SOURCE_FAILED, usage: model requests 7, tool calls 4, tokens 23611/461, cost unknown,
trace 1c8801aa415db157bc92bbcc1046dd4d.
Stage results: RESEARCHING completed (4 requests, 3 tool calls); CRITIQUING completed (2, 1);
SYNTHESIZING not completed, provider_failure: SOURCE_FAILED (1, 0).
model.call spans: 6 × http 200, outcome ok, served_by Nvidia; the 7th: http 200 with span status
ERROR (relay rejected the 200 body; OpenRouter error-in-200 pattern) → SOURCE_FAILED, honestly not an
abstention. After the run: `docker ps -a --filter name=episalpha-worker- --filter name=episalpha-fwd-`
→ none (no leftovers).

## Conclusion for M3-T05
The compose topology's live path is exercised end to end on Linux: worker in the compose sandbox,
forwarder → relay and MCP tool server by name, stage files via the episalpha-stages sub-paths, two
completed stages, honest terminal state. The synthesizer failure is provider-side. Not verified:
a completed live thesis in compose; macOS / Windows (owner checks).
Finding for the final review: a runtime-assembly failure AFTER admission (e.g. relay bind error)
strands the run in QUEUED holding the job slot; preflight now catches the common causes before
admission, but not this class.
```

No new Phoenix verification: `otlp_endpoint` was unset. Earlier G3 Phoenix evidence is
retained. The crash class after admission is not fixed in A15; preflight catches common
causes before admission, and `research recover <run_id>` releases the stranded slot.

### Task 6 — fresh offline G3 checks and records

Step 4 command (exit 0):

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy src/episalpha && uv run pytest -q -m "not live"
```

```text
All checks passed!
83 files already formatted
Success: no issues found in 38 source files
632 passed, 8 deselected in 15.11s
```

Added exact constitution wording, fresh template-based pack, dated append-only G3
re-run block, linked DONE records, M5-T04 next task, HANDOFF §4 rebuild/recovery/check
count/limits, and A15 Findings. Final Step 6 four checks/full diagnose follow below.

Step 6 command (exit 0):

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy src/episalpha && uv run pytest -q -m "not live" && uv run python scripts/diagnose.py
```

```text
All checks passed!
83 files already formatted
Success: no issues found in 38 source files
632 passed, 8 deselected in 16.08s
diagnose: PASS | tests {'passed': 632, 'failed': 0, 'errors': 0, 'skipped': 0} | failures 0 | regressions 0 | orphans 0 | 16.9s
```

Regenerated diagnostics and `implementation/logs/diagnose.jsonl`; no missing files,
status mismatches, regressions or orphan tests. No runtime-code changes, live reruns,
credential reads, branch changes, agents or push. Controller review is separate.

Self-review: read the full tracked diff and both new task records. Restored an incidental
A15 continuation indentation change and removed an unsupported Task 4 baseline claim.
The first record self-check failed (exit 1):

```text
Traceback (most recent call last):
  File "<stdin>", line 24, in <module>
AssertionError: Boundary quote differs from Task 5 continuation
```

A targeted text diff identified one added closing single quote on the host
`open_canonical_db` verdict. Restored the source's exact line in GATE and this journal,
without changing the source report or interpreting the verdict differently. Same
record self-check re-run (exit 0):

```text
Record self-check PASS: exact constitution wording; unchanged earlier G3 and HANDOFF outside §4; verbatim live evidence in 3 records; both verdict blocks in GATE/journal; template sections, one Attempt, DONE links/next task; full diagnose 632 passed, regressions 0, orphans 0.
```
