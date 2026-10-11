# Local Arize Phoenix: runbook (A14, M0-T07)

Phoenix is EpisAlpha's **Diagnose service**: a local UI over the OpenTelemetry spans every
boundary emits. It is diagnostic, never canonical. EpisAlpha runs fully without it, and the
spans then still go to `<data_root>/logs/spans.jsonl` (metadata only).

| Fact | Value (verified against the pinned image on 2026-10-10) |
|---|---|
| Image | `arizephoenix/phoenix:version-20.20.0-nonroot`, pinned as `@sha256:2ac6874a4f743a626060adb6988b6dbd558530a0e06685334f63f8a779aaabb5` |
| License | Elastic License 2.0: free to self-host for personal use; may not be offered as a managed service |
| UI and OTLP/HTTP | `http://127.0.0.1:6006` (UI), `http://127.0.0.1:6006/v1/traces` (OTLP, protobuf). Bound to loopback only. gRPC (4317) and Prometheus (9090) are not published |
| Storage | SQLite at `.episalpha/phoenix/phoenix.db` (git-ignored under `.episalpha/`) |
| Retention | `PHOENIX_DEFAULT_RETENTION_POLICY_DAYS=90` |
| Telemetry | `PHOENIX_TELEMETRY_ENABLED=false`, and `PHOENIX_ALLOW_EXTERNAL_RESOURCES=false` (no self-initiated public-internet requests: fonts, telemetry, WASM download) |
| Process | runs as your host user (`EPISALPHA_UID`/`EPISALPHA_GID`, default 1000), read-only root filesystem, `/tmp` tmpfs, all capabilities dropped, `no-new-privileges`, 1 GiB memory, 256 pids |
| Network | its own bridge network `episalpha-phoenix`; never attached to the research worker's network |

## Start, stop, open

```bash
mkdir -p .episalpha/phoenix                                # once, so the directory is yours
docker compose -f observability/compose.yaml up -d         # start (restarts unless stopped)
docker compose -f observability/compose.yaml logs --tail 20
docker compose -f observability/compose.yaml stop          # stop, keep data
```

Open `http://127.0.0.1:6006`. Real runs appear under project **episalpha**; the live test writes
synthetic traces to project **episalpha-tests**.

## Send EpisAlpha's spans to it

In `config/demo.toml`:

```toml
[observability]
otlp_endpoint = "http://127.0.0.1:6006/v1/traces"   # loopback only; anything else fails validation
capture_content = true                              # full content to Phoenix; JSONL stays metadata-only
```

Each research run is one trace; `session.id` is the run ID, so the Sessions view groups a run.
`episalpha.observability.trace_url(trace_id)` gives `http://127.0.0.1:6006/redirects/traces/<id>`.

## What Phoenix holds

Full content: prompts, completions, tool inputs and outputs, validation detail. Every resolved
credential value is replaced by `***` before any exporter sees a span (verified by the live test).
That content is local to this machine, so treat the database like the research data itself.

## Back up, wipe, upgrade

```bash
# Back up
docker compose -f observability/compose.yaml stop
cp -a .episalpha/phoenix .episalpha/phoenix.bak-$(date -u +%Y%m%d)
docker compose -f observability/compose.yaml start

# Wipe all traces (irreversible)
docker compose -f observability/compose.yaml down
rm -rf .episalpha/phoenix && mkdir -p .episalpha/phoenix
```

Upgrade: back up first, then look up the new `version-X.Y.Z-nonroot` digest
(`docker pull arizephoenix/phoenix:version-X.Y.Z-nonroot`), replace the digest in
`observability/compose.yaml`, run `up -d`, and re-run
`uv run pytest -q -m live tests/integration/test_phoenix_export.py`.

## Known limitation: no login

Authentication is **off**. Turning it on (`PHOENIX_ENABLE_AUTH=true` plus a `PHOENIX_SECRET` of
32+ characters) makes every OTLP client send an API key, which EpisAlpha's exporter does not do
yet. Access control is therefore the loopback binding: any process or user on this machine (and,
under WSL2, the Windows host through localhost forwarding) can read the traces. To enable auth
later: add an `ENV:` reference for the key to `ObservabilityConfig`, send it as the OTLP
`authorization` header, set the two variables above from `.env`, and change the default admin
password at first login.

## Verification record (M0-T07, 2026-10-10)

- `ss -ltn | grep 6006` -> `LISTEN 0 4096 127.0.0.1:6006 0.0.0.0:*`
- `uv run pytest -q -m live tests/integration/test_phoenix_export.py` -> `1 passed`
- Restart: spans in project `episalpha-tests` before 3, after `docker compose restart` 3.
- Phoenix stopped: a span still reached `spans.jsonl`, the caller saw no error and nothing was
  printed.
