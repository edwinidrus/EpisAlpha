# Gate G3: bounded Hermes runtime

**Status:** PASSED 2026-10-11 · owner TODO: rootless Docker or userns-remap (the rootful engine is
hardened only), recorded as the host-engine decision.

## Commands

```bash
uv run pytest -q tests/runtime
set -a; . ./.env; set +a
uv run pytest -q -m live tests/integration/test_hermes_runtime.py tests/integration/test_runtime_boundary.py
uv run python scripts/diagnose.py
# plus the four standard checks
```

## Criteria

- [x] Every tool is snapshot-bound and size-capped, returns typed errors and is hashed. Widening
      attempts fail.
- [x] `compute_derivation` returns host-computed values with `method_version` (A8).
- [x] The relay is fail-closed on unknown routes, enforces every cap, counts retries, redacts
      secrets and sends no `response_format`.
- [x] The Hermes adapter uses probe-verified controls only. The effective tool list equals the
      allowlist.
- [x] The worker cannot read labels or canonical DB, cannot modify evidence or harness, and has
      no unrelated egress. Cancel and timeout kill children within 10 s.
- [x] **A12/A13:**
      - the relay rejects egress-enabling fields (`plugins`, `models`, `:online`, web_search);
      - external DNS does not resolve in the worker;
      - the image is pinned by digest, and the host-engine decision is recorded;
      - after a run, no Hermes skills, memories or `state.db` persist;
      - the skill-set hash is recorded on the run.
- [x] **At least one real-provider run** on the active route (OpenRouter, A9). Docker boundary
      checks alone do not count.
- [x] Recorded:
      - effective tools;
      - model route and `served_by`;
      - runtime and harness hashes;
      - observed budget enforcement;
      - measured cancellation time;
      - requests used against the free-tier daily cap.
- [x] For one real run, a single trace in Phoenix holds `research.run` → `stage.*` →
      `model.call` (`LLM`) and `tool.*` (`TOOL`/`RETRIEVER`) spans, and `repair.attempt` if any.
      Content is visible in Phoenix only. `spans.jsonl` holds hashes only, and no secret appears
      anywhere.

## Results log (append-only; real output only)

### 2026-10-11 06:35 UTC — PASSED

```
uv run pytest -q tests/runtime                                         -> 105 passed
uv run pytest -q -m live tests/integration/test_runtime_boundary.py    -> 3 passed (no model calls)
uv run pytest -q -m live tests/integration/test_hermes_runtime.py      -> run piecewise, see below
uv run python scripts/diagnose.py                                      -> diagnose: PASS | tests 504 passed | failures 0 | regressions 0 | orphans 0
uv run ruff check . / ruff format --check . / mypy src/episalpha       -> clean / 64 files formatted / no issues in 32 files
uv run pytest -q -m "not live"                                         -> 504 passed, 8 deselected
```

The two live model tests ran once each this morning and were **not** re-run as one command,
which would have spent 12 more free-tier requests for no new evidence:
- `test_three_live_stages` (local venv worker), 2026-10-11T06:17:27Z: 1 passed. 6 requests,
  trace `279e56da2fd6b7436795661d00283c7b`.
- `test_three_live_stages_in_the_container` (sandboxed worker), 2026-10-11T06:29:57Z: 1 passed.
  6 requests, trace `f8c7b412beee232c837192a897faff24`.

Recorded:
- **Effective tools:** equal to the allowlist in every stage, with stage-specific lists (M3-T02b).
- **Route:** OpenRouter `nvidia/nemotron-3-ultra-550b-a55b:free`, `served_by` Nvidia on every
  call.
- **Hashes:** worker image `sha256:6d1ed1ee…54cd`; harness hash `de865432…5610`; skill-set hash
  = the empty set.
- **Budget enforcement:** stage caps 4/2/1 with the forced submit on each stage's last request;
  no hidden summary or background requests (relay count = sum of stage requests).
- **Cancellation:** container stopped in 2.57 s on cancel and on timeout.
- **Free-tier requests:** 28 of the 40 approved for the unattended session, including probes and
  one failed attempt.

The trace criterion holds: one Phoenix trace per run, `research.run` -> `stage.*` (AGENT) ->
`model.call` (LLM) and `tool.*` (TOOL/RETRIEVER). There is no `repair.attempt` (the repair loop
is M4-T01). Prompts appear in Phoenix only; `spans.jsonl` holds hashes.

### 2026-10-11 — Re-run after A15 (M3-T05)

**Status:** PASSED 2026-10-11 (re-run after A15). Acceptance met on Linux: compose
isolation and a real-provider run through the worker, forwarder, relay and MCP tool server.
No completed live thesis in compose yet; macOS/Windows owner checks pending; rootless
Docker / userns-remap remains an owner TODO. The supported case abstained because the
real filings are not ingested (G2 owner checkpoint). The synthetic-snapshot run failed
provider-side, `SOURCE_FAILED`; that failure is not relabelled as an abstention or pass.

Fresh Step 4 checks, exit 0:

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy src/episalpha && uv run pytest -q -m "not live"
```

```text
All checks passed!
83 files already formatted
Success: no issues found in 38 source files
632 passed, 8 deselected in 15.11s
```

Boundary evidence quoted from Task 5's **Answer 1 / continuation**, same code,
2026-10-11, not re-run here by controller instruction. Only `relay_via_forwarder` was
ALLOWED; uid 10001; host home and `/stages` BLOCKED in both topologies. Existing
symlink, hardening and exact allowed-set assertions passed unchanged.

Host command (Task 5, exit 0):
`uv run pytest -q -m live tests/integration/test_runtime_boundary.py -s`

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

Compose command (Task 5, exit 0; host-home override avoids the app's `/tmp` collision):

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

Live evidence below is quoted verbatim from the controller's owner-approved run record;
Steps 2–3 were skipped entirely here. Phoenix was on host port 6007, but `otlp_endpoint`
was unset: this new trace was JSONL only, not verified in Phoenix. Earlier Phoenix
evidence above is retained, not replaced or extended by that claim.

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

Final Step 6, after the task records were completed (exit 0):

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

Regenerated `implementation/DIAGNOSTICS.md` and `implementation/logs/diagnose.jsonl`.
