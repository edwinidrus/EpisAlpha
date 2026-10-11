# M0-T04 — Research route moves to OpenRouter (A9)

| Field | Value |
|---|---|
| Status | DONE (2026-10-10) |
| Depends on | M0-T03 |
| Phase constitution | [../CONSTITUTION.md](../CONSTITUTION.md) (inherits [global](../../CONSTITUTION.md)) |
| Plan source | plan §1.2 (route row), §2.6, §3.8; amendments A3, A9 |
| Journal | `tasks/M0-T04-openrouter-route.journal.md` |
| Live calls | **Yes, about 4 requests. Owner approval is required before running.** |

## 0. Context to load

Load these and nothing else:
- `implementation/CONSTITUTION.md`
- `implementation/M0-foundation/CONSTITUTION.md`
- [../PLAN.md](../PLAN.md), the "Known facts about the new route" table
- `config/demo.toml` and `config/demo.example.toml`, the `[provider]` section only
- `config/runtime.lock.json`, the `model_route` section
- `scripts/probe_hermes.py` and `tests/integration/test_hermes_probe.py`
- `src/episalpha/settings.py:94-118` (`ProviderRoute`)

> Structured output **must** come from a forced `tool_choice` on a named function, whose
> arguments the host parses and validates. (plan §2.6.1, A3)

> One verified route; no automatic provider substitution. (plan §1.2)

## 1. Plan

- **Goal:** the active research route is OpenRouter
  `nvidia/nemotron-3-ultra-550b-a55b:free`. It is verified by a real probe, and every observed
  capability is recorded in `config/runtime.lock.json`.
- **In scope:**
  - The config switch.
  - Probe changes for two OpenRouter-specific observations:
    - which provider served the call;
    - whether `response_format` is rejected (HTTP 4xx) rather than ignored.
  - The lock file update (glm-5.3 moves to history).
  - Probe notes.
- **Out of scope:**
  - The relay (M3-T02).
  - Hermes routing (M3-T03).
  - Any `src/episalpha` code change.
- **Files:**
  - `config/demo.toml` and `config/demo.example.toml`, set to:
    - `model_id = "nvidia/nemotron-3-ultra-550b-a55b:free"`
    - `endpoint_url = "https://openrouter.ai/api/v1"`
    - `api_key_env = "ENV:openrouter_api_key"`
  - `scripts/probe_hermes.py`
  - `config/runtime.lock.json`
  - `docs/implementation/hermes_probe.md`
  - Focused test: `tests/integration/test_hermes_probe.py` (`live`).
- **Consumes:**
  - `load_settings` (`src/episalpha/settings.py:347`)
  - `ProviderRoute.credential()` (`settings.py:109`)
  - `probe_tool_call` and `probe_response_format` (`scripts/probe_hermes.py`)
- **Do not:**
  - Hard-code the model name in Python.
  - Print the key.
  - Enable OpenRouter fallbacks.
  - Delete the glm-5.3 evidence.
  - Mark the route verified when a probe fails.

## 2. Verify (before building)

- [ ] **Owner approval** for the live calls, and owner acknowledgement of the unconfirmed
      `:free` data-logging policy. Record both in the journal.
- [ ] `.env` defines `openrouter_api_key` and `openrouter_model`. Check the names only:
      `cut -d= -f1 .env`. Never print values.
- [ ] `openrouter_model` in `.env` equals `nvidia/nemotron-3-ultra-550b-a55b:free`. Use
      `grep '^openrouter_model' .env`; the model name is not a secret.
- [ ] Baseline: the four standard checks are green. Record the counts (expect 305 passed).
- [ ] Re-fetch the public listing (no key needed):
      `curl -s https://openrouter.ai/api/v1/models`. Filter for this id, and journal
      `context_length`, `max_completion_tokens` and `supported_parameters`.

## 3. Build

1. **Probe, OpenRouter observations.** In `scripts/probe_hermes.py`:
   - Add `served_by = response.get("provider")` to `probe_tool_call`'s result.
   - Send `"provider": {"allow_fallbacks": false}` in the payload **only if** a first call
     shows the field is accepted. Record the outcome either way.
   - Make `probe_response_format` catch `urllib.error.HTTPError`. Return
     `{"json_schema_honored": False, "rejected_status": <code>}` instead of crashing. A rejection
     is an observation.
   - Keep the script stdlib-only.
2. **Live test.** Update `test_recorded_capabilities_still_hold` so it compares `served_by`
   against the lock's recorded provider, and so a recorded `rejected_status` is an accepted
   outcome. Never loosen the forced-tool-choice assertions.
3. **Config.** Switch `[provider]` in both TOML files. Keep the glm-5.3 lines as a comment that
   names it as history (route A, verified 2026-09-20).
4. **Run the probe.** Export the key without echoing it:
   `set -a; . ./.env; set +a`
   Then run `uv run python scripts/probe_hermes.py config/demo.toml`.
5. **Lock.**
   - Move the current `model_route` object into `model_route_history[]`.
   - Write the new `model_route` with:
     - `provider: "openrouter"`, `endpoint_url`, `model_id`, `credential_reference`;
     - `observed_capabilities` from the probe output only;
     - `served_by`, `probed_at`, and `free_tier_limits` (marked `"source": "OpenRouter blog 2026, unprobed"`);
     - `data_policy: "unconfirmed; owner acknowledged <date>"`.
6. **Notes.** Add a dated "Route change (A9)" section to `docs/implementation/hermes_probe.md`
   with real probe output. Remove nothing.

## 4. Test

```bash
set -a; . ./.env; set +a
uv run python scripts/probe_hermes.py config/demo.toml
uv run pytest -q -m live tests/integration/test_hermes_probe.py
uv run ruff check . && uv run ruff format --check . && uv run mypy src/episalpha && uv run pytest -q -m "not live"
```

Acceptance:
- [ ] Forced `tool_choice` is honoured and the arguments parse as JSON. If not, report
      **BLOCKED**: the route cannot serve EpisAlpha's structured-output design.
- [ ] `response_format` behaviour is recorded as one of honoured, ignored or rejected. The relay
      design (A3) stays tool_choice-only whatever the result.
- [ ] Usage-reporting presence is recorded, and `served_by` is recorded.
- [ ] Both live tests pass against the new route.
- [ ] Limits re-checked against the observed completion size, and the result recorded:
      - `max_output_tokens_per_call = 4000`. Note whether reasoning tokens count toward it.
      - `max_model_requests = 8`, which gives at most 6 runs/day at 50/day.
- [ ] The default suite still passes offline.

## 5. Diagnose

- [ ] The probe output is pasted in the journal: shortest decisive lines, no secrets.
- [ ] A 429, if seen, is recorded with any `Retry-After` header. It is evidence for the free-tier
      limit.
- [ ] `uv run python scripts/diagnose.py` is not available yet (M0-T05). Record "n/a" in the
      journal.

## 6. Stop and hand off

- **BLOCKED if:**
  - the owner has not approved;
  - the credential is missing;
  - forced tool choice fails;
  - the endpoint refuses every call (for example, the account has no free-tier access).
- **Record:** M0 `PROGRESS.md`, `STATUS.md`, the journal, and the G0 results log entry.
- **Next:** M0-T05.
