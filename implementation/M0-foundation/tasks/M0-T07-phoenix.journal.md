# M0-T07 journal

## Attempt 1 — 2026-10-10 22:38 UTC — claude-opus-5-5
- Owner approval: digest-pinned Docker pulls approved for the unattended session (2026-10-10,
  `docs/implementation/progress.md`, "Unattended overnight build").
- Verify:
  - `docker version` -> server 29.1.3; `docker compose version` -> 2.40.3.
  - Docker Hub tags (2026-10-10): `version-20.20.0-nonroot` = `latest-nonroot`, published
    2026-10-09. `docker pull arizephoenix/phoenix:version-20.20.0-nonroot` -> `Digest:
    sha256:2ac6874a4f743a626060adb6988b6dbd558530a0e06685334f63f8a779aaabb5`. Image user
    `65532`, entrypoint `python3.13 -m phoenix.server.main serve`, exposes 4317/6006/9090.
  - Env names read from the image's own `phoenix/config.py`: `PHOENIX_PORT`, `PHOENIX_HOST`,
    `PHOENIX_WORKING_DIR`, `PHOENIX_SQL_DATABASE_URL`, `PHOENIX_TELEMETRY_ENABLED` ("Master
    toggle for telemetry pixels (FullStory and Scarf.sh) ... Defaults to True"),
    `PHOENIX_ALLOW_EXTERNAL_RESOURCES` ("When False, Phoenix makes no public-internet requests
    on its own initiative"), `PHOENIX_DEFAULT_RETENTION_POLICY_DAYS`, `PHOENIX_ENABLE_AUTH`,
    `PHOENIX_SECRET` (>= 32 chars, a digit and a lowercase letter), `PHOENIX_ADMIN_SECRET`.
  - Routes read from the image: REST `GET /v1/projects/{project_identifier}/spans/otlpv1`
    with `trace_id` filter (`routers/v1/spans.py`); UI route `/redirects/traces/:trace_otel_id`
    in the static bundle, so M0-T06's `trace_url` format is confirmed.
  - Baseline: four checks green (341 passed).
- Decisions:
  - Auth stays OFF: enabling it forces every OTLP client to send an API key, which needs a new
    credential reference and header support in `ObservabilityConfig`. Recorded as a known
    limitation in the runbook; access control is the 127.0.0.1 binding.
  - Bind mount `../.episalpha/phoenix:/data` with `user: "${EPISALPHA_UID:-1000}:..."`: the
    image's uid 65532 cannot write a host directory owned by the owner without sudo, and the
    runbook keeps "back up = copy `.episalpha/phoenix/`".
  - Added `PHOENIX_ALLOW_EXTERNAL_RESOURCES=false` and `HOME=/tmp` (read-only rootfs).
  - The live test writes to project `episalpha-tests`, not `episalpha`, so synthetic traces
    never mix with real runs (the pack said `episalpha`; deviation is deliberate).
- Did: `observability/compose.yaml`, `docs/implementation/phoenix.md`,
  `tests/integration/test_phoenix_export.py` (live).
- Ran:
  - `docker compose -f observability/compose.yaml up -d` -> started; `/healthz` 200; log
    "Phoenix is up and running".
  - `uv run pytest -q -m live tests/integration/test_phoenix_export.py` -> `1 passed in 0.80s`
    (3 spans `model.call`, `research.run`, `tool.search_evidence` under one trace; kinds CHAIN,
    LLM, RETRIEVER; content "synthetic prompt carrying ***"; the secret absent from Phoenix and
    from the JSONL; `trace_url` resolves with 200).
  - `ss -ltn | grep 6006` -> `LISTEN 0 4096 127.0.0.1:6006 0.0.0.0:*`
  - Persistence: spans in `episalpha-tests` before restart 3, after `docker compose restart` 3.
  - `docker inspect` -> `user=1000:1000 ro=true caps=[ALL] sec=[no-new-privileges:true]
    mem=1073741824 pids=256 nets=episalpha-phoenix`, image digest as pinned.
  - Phoenix stopped: a `research.run` span still reached `spans.jsonl` (1 line), exit 0,
    nothing printed. Phoenix started again afterwards.
  - Four checks: All checks passed; 39 files already formatted; no issues in 21 source files;
    341 passed, 3 deselected.
- Outcome: PASS
- Diagnose: see the `diagnose.py` line written after recording.
