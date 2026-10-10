# Gate G0: foundation and integration feasibility

**Status:** offline PASSED (2026-09-20) · live PARTIAL · **reopened** by A9 and A11.

## Commands

```bash
uv run episalpha --version
uv run pytest -q tests/contracts/test_settings.py tests/integration/test_package.py
uv run pytest -q -m live tests/integration/test_hermes_probe.py      # against the ACTIVE route
uv run python scripts/diagnose.py                                    # from M0-T05
uv run pytest -q tests/observability                                 # from M0-T06
# plus the four standard checks
```

## Criteria

- [x] Package installs; `episalpha --version` prints `0.1.0`.
- [x] Settings validate; unknown fields and invalid limits fail; no network on load.
- [x] Hermes API surface read at the pinned commit `c1488ac` / 0.21.3.
- [ ] **Active route verified live.** The OpenRouter route needs M0-T04. The glm-5.3 record is
      history.
- [ ] `scripts/diagnose.py` writes `DIAGNOSTICS.md` and appends `logs/diagnose.jsonl` (M0-T05).
- [ ] Structured logging with redaction tested offline (M0-T06).
- [ ] Owner reviews the probe findings and the data-policy acknowledgement.

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
