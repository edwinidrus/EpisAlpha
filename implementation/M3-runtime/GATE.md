# Gate G3: bounded Hermes runtime

**Status:** not started.

## Commands

```bash
uv run pytest -q tests/runtime
set -a; . ./.env; set +a
uv run pytest -q -m live tests/integration/test_hermes_runtime.py tests/integration/test_runtime_boundary.py
uv run python scripts/diagnose.py
# plus the four standard checks
```

## Criteria

- [ ] Every tool is snapshot-bound and size-capped, returns typed errors and is hashed. Widening
      attempts fail.
- [ ] `compute_derivation` returns host-computed values with `method_version` (A8).
- [ ] The relay is fail-closed on unknown routes, enforces every cap, counts retries, redacts
      secrets and sends no `response_format`.
- [ ] The Hermes adapter uses probe-verified controls only. The effective tool list equals the
      allowlist.
- [ ] The worker cannot read labels or canonical DB, cannot modify evidence or harness, and has
      no unrelated egress. Cancel and timeout kill children within 10 s.
- [ ] **At least one real-provider run** on the active route (OpenRouter, A9). Docker boundary
      checks alone do not count.
- [ ] Recorded:
      - effective tools;
      - model route and `served_by`;
      - runtime and harness hashes;
      - observed budget enforcement;
      - measured cancellation time;
      - requests used against the free-tier daily cap.
- [ ] Events present for one real run: `model.call`, `tool.call`, `stage.transition` and
      `repair.attempt` (if any). Logs contain no prompt or completion text and no secret.

## Results log (append-only; real output only)

_No runs yet._
