# EpisAlpha performance and quality test report — 2026-10-13

**Verdict: PASS with one defect found and fixed.** 19 of 20 planned checks ran; Q10 (live model
quality) is BLOCKED by design. One real defect (a concurrency crash) was found, reproduced,
fixed at its root cause and verified. One dev-only dependency advisory and four improvement
recommendations are open for the owner.

## 0. Summary

| Area | Result | Headline |
|---|---|---|
| ⚡ Performance | ✅ | Every measured path is well inside its target: saved replay 0.29 s (target ≤ 5 s), fake run 0.36–0.6 s, page shows a thesis in 0.9–1.7 s |
| ⚡ Scale | ✅ / 🟡 | 10 000 spans, 1 000 claims, 1 000 scored cases and 112 stored runs all stay fast; two linear paths noted (in-memory evidence search, first Obsidian export) |
| 🟡 Phoenix outage | 🟡 | Runs never fail, but every CLI command waits ~3.5 s instead of ~0.3 s while a configured Phoenix is down |
| 🧪 Quality | ✅ | 95 % line coverage, 11/11 mutants killed (one after adding a test), 0 flakes in 6 full runs, 0 problems in 15 500 fuzz cases, every failure scenario gets its own honest state |
| 🐛 Defect | ✅ fixed | Concurrent `research run` processes could crash with `database is locked`; fixed with `BEGIN IMMEDIATE` |
| 🔒 Security | ✅ / 🟡 | bandit: 0 real findings; pip-audit: `pytest 8.4.2` advisory (dev-only, fix 9.0.3) |
| 🤖 Live model quality | ⛔ | Not testable without owner-approved live calls and the G2 checkpoint |

Machine: WSL2 2.4.13.0, kernel 5.15.167.4, x86_64, Python 3.12.3, Streamlit 1.65.0. Times are
wall-clock on one development machine with other work running; treat them as orders of
magnitude, not a benchmark. Scratch scripts used: `perf.py`, `quality.py`, `mutants.py` (session
scratchpad, not in the repository).

## 1. Test plan

Scope: the offline system at commit `d9e8727` (branch `overnight-m5-m7`). Every run uses the
fake runtime or synthetic data: **no live model calls** (none approved), so model *output*
quality is out of scope and listed as open. Measurements are taken on one machine and are
not a benchmark.

### 1.1 Performance

| ID | What | How | Target / expectation |
|---|---|---|---|
| P1 | CLI cold start | `episalpha --version`, `research status`, 5 runs each | report; < 2 s |
| P2 | Fake research run, end to end | CLI `research run`, 10 runs, median and p95 | report |
| P3 | Saved replay | CLI `replay`, 20 runs after warm-up | ≤ 5 s (plan §14) |
| P4 | Browser render | AppTest: full page render with a finished run and a campaign; real Streamlit first paint in Chromium | report; interactive < 3 s |
| P5 | Evidence scale | snapshot freeze, view build, FTS `search_spans` and `search_evidence` at 100 / 1 000 / 10 000 spans | sub-linear search; no step > 5 s at 10k |
| P6 | Validator scale | `validate` with 10 / 100 / 1 000 claims (incl. derived) | roughly linear |
| P7 | Knowledge and export scale | `relation_table`, `local_graph`, Obsidian export for a run with 1 000 claims | graph capped at 50; export byte-stable |
| P8 | Scoring scale | `score_case` + `pool` over 1 000 outcomes | < 1 s |
| P9 | History growth | 100 fake runs in one data root: DB size, `recent_runs`, replay latency first vs last | flat replay latency |
| P10 | Memory | peak RSS of one fake run in a subprocess | report |
| P11 | Test suite time | `pytest -m "not live" --durations=10` | report slowest tests |

### 1.2 Quality

| ID | What | How | Pass criterion |
|---|---|---|---|
| Q1 | Static checks | ruff, format, mypy strict on `src/`, plus mypy on `apps/` and `scripts/` | clean |
| Q2 | Coverage | `coverage` (temporary tool, not added to the project) over the offline suite | report per module; flag < 80 % |
| Q3 | Mutation spot checks | flip one critical invariant per module (validator recompute, temporal eligibility, snapshot boundary, label sealing, candidate validator, completion metric, replay integrity, secret redaction), run the owning tests, restore | every mutant killed |
| Q4 | Flakiness | full offline suite 3 times in a row | identical results |
| Q5 | Determinism | same inputs twice: snapshot hash, export tree hash, campaign ID, harness hash | identical |
| Q6 | Robustness fuzz | random inputs against contracts (identifiers, decimal strings, spans), candidate validator, worker-result reader, Markdown escaping | only typed refusals; no crash, no escape |
| Q7 | Security scan | `bandit` over `src/` and `pip-audit` over the locked dependencies (temporary tools) | no high-severity finding unexplained |
| Q8 | Single-job safety | two concurrent `submit` + `execute` from two processes | exactly one active job |
| Q9 | Honest failure states | fake scenarios through the CLI: completion, abstention, partial, invalid, provider failure, timeout, cancellation | each maps to its own state and exit code |
| Q10 | Live model quality | thesis quality on real filings | BLOCKED: needs owner-approved live calls and the G2 checkpoint |

## 2. Performance results

### 2.1 Everyday paths

| ID | Measurement | Result | Target | |
|---|---|---|---|---|
| P1 | `episalpha --version` (cold process) | median 0.31 s (n=5) | < 2 s | ✅ |
| P1 | `research status` | median 0.29 s | < 2 s | ✅ |
| P1 | `research status` **with Phoenix configured but down** | median 3.48 s, max 3.59 s (n=3) | — | 🟡 see F2 |
| P2 | fake research run, CLI end to end | median 0.60 s, p95 3.99 s (n=10); repeat of 8 more: 0.36–0.48 s | report | ✅ one cold-start outlier, not reproducible |
| P3 | saved replay after warm-up | median 0.29 s, p95 0.33 s (n=20) | ≤ 5 s | ✅ |
| P4 | full page script render (AppTest, 112 runs in DB) | 0.63 s cold, 0.12 s warm, rerun 0.04 s | report | ✅ |
| P4 | real browser: page load to thesis visible (Chromium) | 1.69 s first, then 0.88–0.99 s | < 3 s | ✅ |
| P10 | peak memory of one CLI fake run | 51.9 MB RSS | report | ✅ |
| P11 | full offline suite | 44–82 s for 731–733 tests; slowest single test 6.6 s (A32, which runs with Phoenix down: F2) | report | ✅ |

### 2.2 Scale

| ID | Size | Result | |
|---|---|---|---|
| P5 | 100 / 1 000 / 10 000 spans | snapshot freeze 0.000 / 0.001 / 0.011 s; view build 0.000 / 0.004 / 0.431 s; DB save 0.005 / 0.049 / 0.48 s; **SQLite FTS search 0.1 / 0.3 / 2.2 ms**; **worker `search_evidence` 0.3 / 6.7 / 447 ms** | ✅ / 🟡 F3 |
| P6 | validator, 10 / 100 / 1 000 claims (+10 % derived) | 0.000 / 0.001 / 0.008 s; 2 302 checks at 1 000; all valid | ✅ linear |
| P7 | knowledge view, 1 000 claims | relation table 2 019 rows in 6 ms; graph capped at 50 nodes, truncation flagged, 7 ms | ✅ |
| P7 | Obsidian export, 1 000 claims | first export 1 013 files in 10.6 s; re-export 0.19 s; byte-stable ✅ | 🟡 F4 |
| P8 | score 1 000 cases + pool | 21 ms + 4 ms | ✅ |
| P9 | 112 runs in one data root | in-process run 0.18 s (first 10) vs 0.13 s (last 10); replay 0.8 ms first and last; recent-runs 1.5 ms; DB 1.55 MB, data root 3.0 MB | ✅ flat |

## 3. Quality results

| ID | Check | Result | |
|---|---|---|---|
| Q1 | ruff, format, mypy strict (`src/`), mypy on `apps/` + `scripts/` | all clean. Note: checking `apps/` alone reports `missing py.typed`, and an incremental mypy cache can show two false `attr-defined` errors; `--no-incremental` is clean (F6) | ✅ |
| Q2 | line coverage, offline suite | **95 %** (6 001 statements). Lowest: `runtime/sandbox.py` 85 % (Docker-only paths), `cli.py` 90 %, `storage/db.py` 91 %, `model_relay.py` 91 %; 15 modules at 98–100 % | ✅ |
| Q3 | mutation spot checks (11 invariants) | **11/11 killed** — derivation recompute, temporal eligibility, snapshot span boundary, label sealing, candidate path, completion metric, artifact hash check, secret redaction, relay web-search refusal, canonical-ID reuse, provider-failure-is-not-abstention. Artifact-hash mutant first **survived** (replay verifies separately; scoring and resume rely on `read()` alone) -> added `test_scoring_refuses_a_tampered_artifact`, now killed. Source restored and git-clean after every mutant | ✅ |
| Q4 | flakiness | 6 full runs today (3 back to back): identical pass counts, 0 failures | ✅ |
| Q5 | determinism | snapshot hash identical across freeze times and span order; harness hash stable; export byte-stable (P7); campaign ID `camp-880570ebbcb2b6c1` identical across three fresh data roots | ✅ |
| Q6 | fuzz, 15 500 random inputs | identifiers, decimal values (floats, NaN, `1e999`, strings), span offsets, 3 000 random candidate proposals, 500 random worker result files, file names: **0 crashes, 0 wrong acceptances**; no candidate accepted; 1 random identifier accepted and it was valid. **Not fuzzed:** the browser's Markdown escaping helpers (they live inside the Streamlit script); covered instead by the existing inert-text UI tests | ✅ |
| Q7 | bandit (`src/`) | 44 notes: 39 low (27 `assert`, subprocess use); 5 medium, all false positives (fixed table names in SQL, compose-only `0.0.0.0` bind by design, container tmpfs flag) | ✅ |
| Q7 | pip-audit (66 locked packages) | **`pytest 8.4.2` PYSEC-2026-1845, fixed in 9.0.3** — dev dependency only, not in the runtime image | 🟡 F5 |
| Q8 | single-job safety, 3 concurrent CLI runs | invariant held (never two active jobs, no leftover lease) but **one process crashed with `database is locked`** in 2 of 7 rounds -> **fixed** (F1); after the fix 10/10 rounds: one admitted, two clean refusals, 0 crashes | ✅ fixed |
| Q9 | honest states via CLI | completion -> COMPLETED/0; abstention -> ABSTAINED/5; partial -> PARTIAL/5; invalid references -> REJECTED/3 INVALID_OUTPUT; provider failure -> FAILED/4 SOURCE_FAILED; timeout -> TIMED_OUT/4 BUDGET_EXCEEDED; cancellation -> CANCELLED/6; repaired -> COMPLETED/0 with warning | ✅ |
| Q10 | live model quality on real filings | not run: needs owner-approved live calls and the G2 checkpoint | ⛔ |

## 4. Findings

| # | Severity | Finding | Status |
|---|---|---|---|
| F1 | 🔴 Medium | **Concurrent admissions could crash.** `storage.db.transaction` began DEFERRED; `admit()` reads then writes, and after another process commits SQLite cannot upgrade the stale read snapshot, so it fails immediately with `database is locked` (busy timeout not applied). User impact: a traceback instead of "a research job is already active". | ✅ **Fixed**: `BEGIN IMMEDIATE`. Red test `tests/research/test_runner.py::test_concurrent_admissions_refuse_cleanly_instead_of_crashing` reproduced the exact error; full suite 733 passed after the fix |
| F2 | 🟠 Low-medium | **Phoenix outage slows every CLI command ~12×** (0.29 s -> ~3.5 s) when `otlp_endpoint` is set and Phoenix is down: the exporter waits at shutdown. Runs still succeed (A32 holds). | Open. Option: probe the endpoint once at start-up (≈50 ms) and use the JSONL fallback only when it is down, or lower `export_timeout_seconds`. Owner choice |
| F3 | 🟡 Low | Worker `search_evidence` scans the snapshot in memory: 447 ms per call at 10 000 spans (SQLite FTS does it in 2 ms). Fine for v0.1 corpora (tens to hundreds of spans). | Open, by design for now |
| F4 | 🟡 Low | First Obsidian export of a 1 000-claim run takes 10.6 s (about 10 ms per file, durable writes); re-export 0.19 s. | Open, acceptable |
| F5 | 🟡 Low | `pytest 8.4.2` has advisory PYSEC-2026-1845 (fix 9.0.3). Dev/test only. | Open: upgrade with `uv add --dev "pytest>=9.0.3"` in its own change and re-run the suite |
| F6 | ⚪ Info | Package has no `py.typed` marker, so type-checking `apps/` or `scripts/` on their own treats `episalpha` as untyped; a stale mypy cache produced two false errors. Gate command (`mypy src/episalpha`) unaffected. | Open: add an empty `src/episalpha/py.typed` if apps/scripts should be type-gated |
| F7 | ⚪ Info | Test gap: `RunArtifacts.read()`'s own hash check had no direct test outside replay. | ✅ Closed by `test_scoring_refuses_a_tampered_artifact` |

## 5. What changed in the repository during this test campaign

- `src/episalpha/storage/db.py`: `BEGIN IMMEDIATE` (F1).
- `tests/research/test_runner.py`: concurrency regression test (F1).
- `tests/evaluation/test_scoring.py`: tampered-artifact test (F7).
- `docs/implementation/progress.md`: F1 recorded under findings.
- This report.

Final state: ruff, format, mypy clean; `pytest -m "not live"` **733 passed**; `diagnose.py` ->
`PASS | tests {'passed': 733, ...} | failures 0 | regressions 0 | orphans 0`. Not committed.
