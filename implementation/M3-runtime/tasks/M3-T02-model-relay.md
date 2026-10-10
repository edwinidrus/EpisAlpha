# M3-T02 — Single-route model relay

| Field | Value |
|---|---|
| Status | TODO |
| Depends on | M3-T01, M0-T04 |
| Phase constitution | [../CONSTITUTION.md](../CONSTITUTION.md) (inherits [global](../../CONSTITUTION.md)) |
| Plan source | plan §9 M3-T02 card, §2.6, §3.8; amendments A3, A9 |
| Journal | `tasks/M3-T02-model-relay.journal.md` |

## 0. Context to load

Load these and nothing else:
- `implementation/CONSTITUTION.md`
- `implementation/M3-runtime/CONSTITUTION.md`, articles 4–7 and 11
- [../PLAN.md](../PLAN.md), "Route facts" and open question 2
- `config/runtime.lock.json`, the `model_route` written by M0-T04. **Use its observed values,
  not the plan's.**
- `src/episalpha/settings.py:94-118` (`ProviderRoute`) and `:263-308` (`Limits`, including the
  `eur_cap` ponytail note)
- `src/episalpha/contracts/research.py:281-290` (`Usage`)
- `src/episalpha/observability.py`
- `scripts/probe_hermes.py`, which shows the exact request shape that worked live

> The relay must **not** send `response_format`. Structured output comes from a forced
> `tool_choice` on a named function whose arguments the relay parses and validates. (A3)

> Implement only the endpoint/features actually used by the pinned Hermes path. No
> general-purpose model gateway, routing optimization, or invented OpenAI compatibility. (plan
> M3-T02 scope)

## 1. Plan

- **Goal:** a trusted relay, the only thing holding the provider key. It forwards worker model
  requests to the one configured route, enforces every per-run budget, and accounts usage
  honestly.
- **Files:**
  - `src/episalpha/runtime/model_relay.py`
  - `src/episalpha/settings.py` only if a verified probe requires a new field; if so, record
    the reason
  - Focused test: `tests/runtime/test_model_relay.py`, using a local fake provider (an injected
    transport, or a loopback `http.server` fixture)
- **Produces:** `class ModelRelay(route: ProviderRoute, limits: Limits, run_token: str, transport=...)`.
  - `forward(request_body: bytes, presented_token: str) -> RelayResponse`.
  - Request checks:
    - Reject a token mismatch with `NOT_AUTHORIZED`.
    - Reject a model other than `route.model_id` and a path other than `/chat/completions`.
    - Strip or reject `response_format` (reject, and log the attempt).
    - Clamp or reject `max_tokens` above `max_output_tokens_per_call`.
    - Reject a body larger than `max_request_body_bytes`.
    - Add `provider: {"allow_fallbacks": false}` **only if M0-T04 recorded it as accepted**.
  - Budgets:
    - Each upstream attempt, retries included, decrements one run-global counter. At zero the
      result is `BUDGET_EXCEEDED` and no call is made.
    - At most `max_transport_retries`, and only for explicitly transient failures: connection
      reset, 502, 503 and 504. A **429** honours `Retry-After` only within the remaining wall
      time, otherwise it is a provider failure.
  - Usage:
    - Prompt and completion tokens come from the response `usage`, or `None` when absent.
    - `cost_eur` is always `None`.
    - `served_by` is read from the response `provider` field.
  - Every attempt emits a `model.call` event. Credential values are never logged and never
    returned.
  - `cancel()` closes the in-flight request.
- **Remove the `eur_cap` ponytail block in `settings.py` only if** this task implements cost
  reservation. It does not, so **leave it**.
- **Out of scope:** streaming (unless pinned Hermes requires it, with evidence), multiple
  routes, caching, and pricing.
- **Do not:**
  - Trust advertised capabilities over `runtime.lock.json`.
  - Reset a budget on a new stage or worker restart. The counter lives in the relay instance,
    and the runner (M4) persists it.

## 2. Verify (before building)

- [ ] `config/runtime.lock.json` has the M0-T04 OpenRouter `model_route` with
      `verified: true`. **If not, BLOCKED.**
- [ ] Find out which endpoint or endpoints pinned Hermes calls, and whether it streams. Read
      `run_agent.py` at `c1488ac`, or capture traffic once through a logging stub. Journal the
      evidence.
- [ ] Baseline: the four checks and `diagnose.py` are green.
- [ ] **Red first.** Write `tests/runtime/test_model_relay.py`. Cover:
  - A wrong token, an unknown model and an unknown path are rejected.
  - `response_format` is rejected.
  - Oversize body; `max_tokens` cap.
  - The request budget across "stages", with no reset.
  - Retries count toward the budget.
  - A 429 with a long `Retry-After` and a short remaining wall time is a provider failure.
  - Missing `usage` gives `None`, not `0`.
  - The secret is absent from the response and the logs.
  - `served_by` is captured.
  - Cancellation closes the request.
  - Plus one test the plan requires: a recorded fixture of the provider's `response_format`
    behaviour (from M0-T04), asserted, so that a provider change gets noticed.

## 3. Build

1. Write the request validation pipeline as pure functions.
2. Write the budget counter and the retry policy.
3. Write the transport call, with the key header injected here only.
4. Write usage extraction and event emission.

## 4. Test

```bash
uv run pytest -q tests/runtime/test_model_relay.py
uv run ruff check . && uv run ruff format --check . && uv run mypy src/episalpha && uv run pytest -q -m "not live"
```

Acceptance:
- [ ] Unknown routes or models fail closed.
- [ ] Request-size, output and request-count caps apply.
- [ ] Missing usage is explicit.
- [ ] Secrets are redacted.
- [ ] Retries count.
- [ ] Cancellation closes requests.
- [ ] Budgets are not reset by a new stage or worker retry.
- [ ] No `response_format` ever leaves the relay.

## 5. Diagnose

- [ ] `diagnose.py`: no regression.
- [ ] Sample `model.call` lines are in the journal: success, retry, budget exhausted.
- [ ] The journal states the Hermes endpoint evidence and the observed reasoning-token
      behaviour against `max_tokens`.

## 6. Stop and hand off

- **BLOCKED if:**
  - the route is unverified;
  - Hermes requires streaming or endpoints beyond what the plan allows, without owner approval.
- **Record:** M3 `PROGRESS.md`, `STATUS.md`, and the journal.
- **Next:** M3-T03.
