# M0 phase report: foundation and integration feasibility

**Gate G0: PASSED on 2026-10-10** (re-run after amendments A9, A11 and A14). One owner item is
open: review the route probe findings. Written at the end of the unattended build session
(2026-10-10/11). Real command output lives in [PROGRESS.md](PROGRESS.md), [GATE.md](GATE.md)
and the task journals.

## What M0 delivers

| Task | Status | What exists now |
|---|---|---|
| M0-T01 | DONE (2026-09-20) | Python 3.12 package, `episalpha --version`, ruff/mypy/pytest set-up |
| M0-T02 | DONE (2026-09-20) | One validated `Settings` object; `ENV:` credential references only |
| M0-T02b | DONE (2026-09-20) | Source families with provenance (primary / secondary / unverified) |
| M0-T03 | DONE (2026-09-20) | Hermes API surface read at pinned commit `c1488ac` / 0.21.3; first route probe |
| **M0-T04** | **DONE (2026-10-10)** | Research route moved to **OpenRouter `nvidia/nemotron-3-ultra-550b-a55b:free`**, verified live |
| **M0-T05** | **DONE (2026-10-10)** | `scripts/diagnose.py`: one command for the health of the build |
| **M0-T06** | **DONE (2026-10-10)** | `episalpha.observability`: OpenTelemetry spans for every boundary |
| **M0-T07** | **DONE (2026-10-10)** | Local Arize Phoenix on `127.0.0.1:6006`, pinned by digest |

## Key evidence

- **Route (M0-T04).** Forced `tool_choice` honoured, arguments parse as JSON, served by
  `Nvidia`, `provider.allow_fallbacks: false` accepted. A trivial call used 213 output tokens
  (122 reasoning). Live tests: `2 passed in 11.36s`. 4 free-tier requests spent.
- **Diagnose script (M0-T05).** `diagnose: PASS | tests 324 → 341 passed | failures 0 |
  regressions 0 | orphans 0 | ~5 s`. It checks 41 file paths named by DONE rows and finds none
  missing.
- **Tracing (M0-T06).** 17 focused tests. A secret placed in attributes, events, sequences and
  an exception message appears in neither exporter. The JSONL fallback keeps only hashes and
  sizes for content. An unreachable Phoenix never reaches the caller. The default test suite
  now has a network guard: any connection or DNS lookup outside loopback fails the test.
- **Phoenix (M0-T07).** One synthetic trace with 3 spans arrives, with the kinds shown and the
  secret replaced by `***`. Port bound to `127.0.0.1` only. Data survives a restart. With Phoenix
  stopped, spans still reach the JSONL and nothing fails.

## Numbers

| Measure | Before M0 re-open | After |
|---|---:|---:|
| Default-suite tests | 305 | 341 |
| Source files under strict mypy | 20 | 21 |
| Runtime dependencies | pydantic, typer | + opentelemetry-api, -sdk, -exporter-otlp-proto-http (1.45.1) |
| Live model requests spent | — | 4 |

## Deviations from the packs (all recorded in the journals)

1. **`tests/contracts/test_settings.py` changed in M0-T04.** It hard-coded `"glm-5.3"`. It now
   compares the example config with the verified route in the lock, which keeps model names out
   of test code.
2. **`tests/conftest.py` changed in M0-T06.** The network guard has to cover the whole default
   suite, and conftest is the only place that does.
3. **`export_timeout_seconds` added** to `ObservabilityConfig`, so an absent Phoenix cannot
   stall a flush.
4. **Phoenix runs as the host user (uid 1000)**, not as the image's uid 65532, so the
   bind-mounted data directory stays writable without sudo.
5. **Live Phoenix test traces go to project `episalpha-tests`**, never mixed with real runs.

## Known limitations and open items

- **Phoenix has no login.** Enabling auth needs API-key support in the exporter. Anyone on
  this machine, including the Windows host through WSL2 localhost forwarding, can read the
  traces. The runbook has the steps to enable it.
- **`response_format` returned JSON once on the new route.** That is weak evidence, since the
  parameter isn't listed for `:free`. The relay stays tool-choice-only (A3).
- **Free-tier limits are still untested.** No 429 was seen.
- **Owner:** review `docs/implementation/hermes_probe.md` §8, the last unticked G0 item.

## Where to look

- Probe: `docs/implementation/hermes_probe.md` §8, `config/runtime.lock.json`
- Diagnose: `implementation/DIAGNOSTICS.md`, `implementation/logs/diagnose.jsonl`
- Phoenix: `docs/implementation/phoenix.md`; UI at `http://127.0.0.1:6006`
