# Gate G0: foundation and integration feasibility

**Status:** PASSED 2026-10-10 (re-run after A9/A11/A14) · owner review of the probe findings
outstanding · Hermes end-to-end carried to M3 by design.

## Commands

```bash
uv run episalpha --version
uv run pytest -q tests/contracts/test_settings.py tests/integration/test_package.py
uv run pytest -q -m live tests/integration/test_hermes_probe.py      # against the ACTIVE route
uv run python scripts/diagnose.py                                    # from M0-T05
uv run pytest -q tests/observability                                 # from M0-T06
docker compose -f observability/compose.yaml up -d                   # from M0-T07
uv run pytest -q -m live tests/integration/test_phoenix_export.py    # from M0-T07
# plus the four standard checks
```

## Criteria

- [x] Package installs; `episalpha --version` prints `0.1.0`.
- [x] Settings validate; unknown fields and invalid limits fail; no network on load.
- [x] Hermes API surface read at the pinned commit `c1488ac` / 0.21.3.
- [x] **Active route verified live.** OpenRouter Nemotron 3 Ultra `:free`, M0-T04, 2026-10-10.
      The glm-5.3 record is history.
- [x] `scripts/diagnose.py` writes `DIAGNOSTICS.md` and appends `logs/diagnose.jsonl` (M0-T05).
- [x] OpenTelemetry tracing works offline. The JSONL fallback holds metadata only, and redaction
      holds in both exporters (M0-T06).
- [x] Spans reach the local Phoenix as one trace tree. Phoenix is bound to 127.0.0.1 and
      persists across restarts, with telemetry off and the image pinned by digest (M0-T07).
- [ ] Owner reviews the probe findings (`docs/implementation/hermes_probe.md` §8). The
      data-policy acknowledgement was given on 2026-10-11.

Not part of G0: Hermes end-to-end with EpisAlpha tools (M3-T01/M3-T03).

## Results log (append-only; real output only)

### 2026-09-20 — offline PASSED, live PARTIAL (route: Ollama `glm-5.3`, now history)

```
uv run episalpha --version                                        -> 0.1.0
uv run pytest -q tests/contracts/test_settings.py tests/integration/test_package.py -> passed
uv run pytest -q -m live tests/integration/test_hermes_probe.py   -> 2 passed in 16.93s
```

The model route was verified at the time. The Hermes side was not fully verified:
- **Install path:** a `git+https` wheel build is refused upstream on purpose. The editable clone
  at `c1488ac` worked. M3 uses the Docker image.
- **Tool path:** identified, not proven. `AIAgent.__init__` exposes no tool injection, so tools
  must arrive over MCP (`mcp.json`, `mcp_` prefix, `create_custom_toolset` allowlist).
- **No end-to-end Hermes agent turn was run.**

Full findings: `docs/implementation/hermes_probe.md`; machine-readable record:
`config/runtime.lock.json`.

### 2026-10-10 — active route verified live (route: OpenRouter `nvidia/nemotron-3-ultra-550b-a55b:free`, M0-T04)

```
uv run python scripts/probe_hermes.py config/demo.toml           -> exit 0; forced tool_choice honoured; served_by Nvidia
uv run pytest -q -m live tests/integration/test_hermes_probe.py   -> 2 passed in 11.36s
uv run pytest -q -m "not live"                                    -> 305 passed, 2 deselected
```

G0 stays reopened: M0-T05, M0-T06 and M0-T07 are still open, and the owner review of the probe
findings is pending.

### 2026-10-10 22:45 UTC — G0 re-run after A9, A11, A14: PASSED (owner review outstanding)

```
uv run episalpha --version                                                   -> 0.1.0
uv run pytest -q tests/contracts/test_settings.py tests/integration/test_package.py -> 42 passed
uv run pytest -q tests/observability                                         -> 17 passed
uv run python scripts/diagnose.py                                            -> diagnose: PASS | tests 341 passed | failures 0 | regressions 0 | orphans 0 | 5.5s
docker compose -f observability/compose.yaml up -d                           -> started, /healthz 200
uv run pytest -q -m live tests/integration/test_phoenix_export.py            -> 1 passed
uv run ruff check . / ruff format --check . / mypy src/episalpha             -> clean / 39 files formatted / no issues in 21 files
uv run pytest -q -m "not live"                                               -> 341 passed, 3 deselected
```

The live route test (`tests/integration/test_hermes_probe.py`) was not re-run: it passed at
22:19 UTC the same evening (M0-T04, 2 passed), and re-running would spend 2 more free-tier
requests for no new evidence. Open: the owner's review of `docs/implementation/hermes_probe.md`
§8. Not part of G0: Hermes end-to-end with EpisAlpha tools (M3).
