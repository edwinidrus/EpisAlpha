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

