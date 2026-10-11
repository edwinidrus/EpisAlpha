# M0-T07 — Local Arize Phoenix diagnose service (A14)

| Field | Value |
|---|---|
| Status | DONE |
| Depends on | M0-T06 |
| Phase constitution | [../CONSTITUTION.md](../CONSTITUTION.md) (inherits [global](../../CONSTITUTION.md)) |
| Plan source | amendment A14 |
| Journal | `tasks/M0-T07-phoenix.journal.md` |
| Network | Pulls one Docker image. No model calls. |

## 0. Context to load

Load these and nothing else:
- `implementation/CONSTITUTION.md`, §VII, articles 28–29 (never canonical, content policy)
- `implementation/M0-foundation/CONSTITUTION.md`, articles 5–6
- `src/episalpha/observability.py` (M0-T06): `configure_tracing`, `span`, `trace_url`
- `src/episalpha/settings.py`, `ObservabilityConfig`

Phoenix facts researched on 2026-10-10. Re-verify each one:
- **License:** Elastic License 2.0. Free to self-host for personal use; it may not be offered as
  a managed service.
- **Image:** `arizephoenix/phoenix`, with tags `version-X.Y.Z`, `latest-nonroot` and so on.
- **Ports:** UI and OTLP/HTTP `/v1/traces` on **6006**; gRPC on 4317, which is not used here.
  OTLP/HTTP is documented as protobuf.
- **Environment:**
  - `PHOENIX_PORT` (6006), `PHOENIX_HOST` (0.0.0.0);
  - `PHOENIX_WORKING_DIR`;
  - `PHOENIX_SQL_DATABASE_URL` (SQLite or Postgres; unset means a temporary SQLite file that is
    lost);
  - `PHOENIX_TELEMETRY_ENABLED` (default `true`, set it `false`);
  - `PHOENIX_DEFAULT_RETENTION_POLICY_DAYS` (default `0`, meaning infinite).
- **Auth:** OAuth2, LDAP or local accounts. The exact environment variable names are **not
  yet verified**.

## 1. Plan

- **Goal:** a local, persistent, private Phoenix that receives EpisAlpha's spans over OTLP. You
  can open it at `http://127.0.0.1:6006`. Nothing outside this machine, including the Hermes
  worker container, can reach it.
- **Files:**
  - `observability/compose.yaml` (new)
  - `docs/implementation/phoenix.md`, the runbook (new)
  - Focused test: `tests/integration/test_phoenix_export.py` (`live`, because it needs Docker)
- **`compose.yaml`:**
  - One service, `phoenix`. The image is the `-nonroot` variant **pinned by digest**.
  - `ports: ["127.0.0.1:6006:6006"]`, loopback only, with no 4317.
  - Volume `../.episalpha/phoenix:/data`, with
    `PHOENIX_SQL_DATABASE_URL=sqlite:////data/phoenix.db` and `PHOENIX_WORKING_DIR=/data`.
  - `PHOENIX_TELEMETRY_ENABLED=false`, and `PHOENIX_DEFAULT_RETENTION_POLICY_DAYS=90`.
  - Authentication enabled, if the verified variables allow it. The secret is
    `ENV:phoenix_secret` from `.env`, never a literal value.
  - Hardening: `read_only: true` with `/tmp` tmpfs, `cap_drop: [ALL]`,
    `security_opt: [no-new-privileges:true]`, memory and pids limits, `restart: unless-stopped`.
  - Its own network. It is **never** attached to the M3 worker network.
- **Runbook:** start and stop (`docker compose -f observability/compose.yaml up -d`), the UI
  URL, how to set `[observability] otlp_endpoint`, backup (stop, then copy
  `.episalpha/phoenix/`), retention, upgrade (new digest, back up first), and how to wipe it.
- **Out of scope:**
  - Postgres.
  - gRPC.
  - Remote access.
  - The diagnostics pull (M8-T05).
- **Do not:**
  - Expose port 6006 on `0.0.0.0`.
  - Commit `.episalpha/phoenix/`. It is git-ignored under `.episalpha/`.
  - Put Phoenix on the worker network.

## 2. Verify (before building)

- [ ] `docker compose version` works. Pull the chosen `version-X.Y.Z-nonroot` tag and journal
      its digest.
- [ ] Verify the exact auth environment variable names in the current Phoenix docs or the
      image's `--help`. If auth cannot be enabled simply, record that, and rely on the loopback
      binding. Report it as a known limitation, not a silent skip.
- [ ] Verify `PHOENIX_SQL_DATABASE_URL` persistence. Restart the container and confirm a span
      survives.
- [ ] Baseline: the four standard checks are green.

## 3. Build

1. Write `compose.yaml`, then start Phoenix and open the UI to check it.
2. Write the runbook.
3. Write the live test:
   - configure tracing with `otlp_endpoint=http://127.0.0.1:6006/v1/traces`;
   - emit a synthetic `research.run` trace with one `LLM` child and one `TOOL` child;
   - force-flush;
   - query Phoenix (REST or GraphQL; record which) and assert that the trace and its 3 spans
     exist under project `episalpha`;
   - assert that a `TEST_SECRET` value placed in an attribute is not present.

## 4. Test

```bash
docker compose -f observability/compose.yaml up -d
uv run pytest -q -m live tests/integration/test_phoenix_export.py
uv run ruff check . && uv run ruff format --check . && uv run mypy src/episalpha && uv run pytest -q -m "not live"
```

Acceptance:
- [ ] Spans reach Phoenix and appear as one trace tree, with OpenInference kinds shown.
- [ ] Redaction holds in Phoenix.
- [ ] The port is bound to `127.0.0.1` only (`ss -ltnp | grep 6006`).
- [ ] Data persists across a restart.
- [ ] Telemetry is off.
- [ ] Retention is set.
- [ ] The image is pinned by digest.
- [ ] With Phoenix stopped, an EpisAlpha span still goes to the JSONL and nothing fails.

## 5. Diagnose

- [ ] Journal: a screenshot description, or the API response, showing the synthetic trace tree.
- [ ] `diagnose.py`: no regression.
- [ ] Re-run G0 and append the result to `../GATE.md`.

## 6. Stop and hand off

- **BLOCKED if:** Docker is unavailable, or the image cannot be pinned. The offline JSONL path
  from M0-T06 still works, so report that separately.
- **Record:** M0 `PROGRESS.md`, `STATUS.md`, and the journal.
- **Next:** M1-T05.
