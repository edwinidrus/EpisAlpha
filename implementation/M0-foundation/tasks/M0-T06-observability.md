# M0-T06 — Runtime observability foundation (A11)

| Field | Value |
|---|---|
| Status | TODO |
| Depends on | M0-T02 |
| Phase constitution | [../CONSTITUTION.md](../CONSTITUTION.md) (inherits [global](../../CONSTITUTION.md)) |
| Plan source | amendment A11; blueprint §15.2 (trace model), for reference only |
| Journal | `tasks/M0-T06-observability.journal.md` |

## 0. Context to load

Load these and nothing else:
- `implementation/CONSTITUTION.md`, articles 26–30
- `implementation/M0-foundation/CONSTITUTION.md`, article 6
- `src/episalpha/settings.py`:
  - `PathsConfig` (`:77`)
  - `ProviderRoute.credential()` (`:109`)
  - `SourceConfig.credential()` (`:189`)
  - `Settings` (`:310`)
  - `load_settings` (`:347`)
- `tests/contracts/test_settings.py`, house test style

## 1. Plan

- **Goal:** one small module through which every later boundary emits structured, correlated,
  redacted JSON-lines events, without the event stream ever becoming canonical state.
- **In scope:**
  - `EventName(StrEnum)`, a frozen event vocabulary. Adding a name is a one-line change, so the
    enum stops typos rather than restricting design. The names:
    - `connector.request`, `connector.response`, `connector.refused`
    - `snapshot.built`
    - `tool.call`
    - `model.call`
    - `stage.transition`
    - `repair.attempt`
    - `validation.completed`
    - `run.terminal`
  - `bind(**ids)`, a context manager over `contextvars` for `run_id`, `stage`, `task_id` and
    `attempt`. Nested binds merge, and leaving a bind restores the outer values.
  - `event(name: EventName, /, **fields)`, which emits one record carrying these fields:
    - `ts` (UTC ISO with offset)
    - `event`
    - `level`
    - the bound ids
    - `fields`

    `Decimal` is serialised to `str`, `datetime` to ISO with offset, and `Path` to `str`.
    Anything else that is not JSON-safe goes through `repr()`, truncated to 200 characters.
  - `JsonLinesFormatter(logging.Formatter)`.
  - `RedactionFilter(secrets: Iterable[str])`, which replaces every occurrence of each non-empty
    secret with `***` in the message and in every string field, at any depth.
  - `configure_logging(settings: Settings) -> Path`:
    - attaches a file handler at `<data_root>/logs/episalpha.jsonl` and creates the directory;
    - installs the redaction filter, built from every resolved credential (provider plus all
      sources);
    - is idempotent: calling it twice adds no second handler;
    - returns the log path.
  - `timed(name, **fields)`, a context manager that emits one event with `duration_ms` and
    `outcome` (`ok`, or the exception class name), and re-raises.
- **Out of scope:**
  - Instrumenting existing modules (M2-T06 and later tasks).
  - Log rotation.
  - Console pretty-printing.
  - OpenTelemetry.
  - Metrics backends.
- **Files:** `src/episalpha/observability.py` + `tests/observability/test_observability.py`.
- **Produces:** `EventName`, `bind`, `event`, `timed`, `JsonLinesFormatter`, `RedactionFilter`,
  `configure_logging`.
- **Do not:**
  - Log payload bodies or prompts. Log hashes, sizes, IDs, counts and durations.
  - Read logs from application logic.
  - Write to stdout or stderr by default, because that would pollute CLI output in M4.
  - Let a logging failure crash the caller. `logging` already swallows handler errors; keep it
    that way.

## 2. Verify (before building)

- [ ] `settings.paths.data_root` is an absolute `Path` (`PathsConfig`, `settings.py:77-91`;
      seen 2026-10-10). Re-check it with `grep -n "data_root" src/episalpha/settings.py`.
- [ ] Baseline: the four standard checks are green.
- [ ] Write the tests first, using `tmp_path` and a synthetic `Settings` whose credential env
      var is set with `monkeypatch.setenv("TEST_SECRET", "s3cr3t-value")`. They must fail
      before the module exists. The tests:
  - Event shape and JSON validity.
  - `bind` nesting and restore.
  - `Decimal` and `datetime` serialisation.
  - A secret inside the message, a field and a nested field is redacted.
  - `configure_logging` is idempotent.
  - `timed` records `outcome` on success and on exception, and re-raises.
  - Context does not leak across threads: a fresh `contextvars` context shows no bound ids.

## 3. Build

1. Write the vocabulary, `bind` and `event` on a module logger `logging.getLogger("episalpha")`
   with `propagate = False`.
2. Write the formatter and redaction filter, with recursive string replacement over dicts,
   lists and tuples.
3. Write `configure_logging`. Mark the handler with an attribute so the idempotence check is
   exact.
4. Write `timed`, using `time.perf_counter()`.

## 4. Test

```bash
uv run pytest -q tests/observability
uv run ruff check . && uv run ruff format --check . && uv run mypy src/episalpha && uv run pytest -q -m "not live"
```

Acceptance:
- [ ] Every test listed under Verify passes, and strict mypy is clean for the new module.
- [ ] A redaction test proves the literal secret appears **nowhere** in the written file, by
      grepping the file content in the test.
- [ ] The default suite is still offline and green.
- [ ] There are no new dependencies (`git diff pyproject.toml` is empty).

## 5. Diagnose

- [ ] `uv run python scripts/diagnose.py`: the test count rises by the new tests, and there is
      no regression.
- [ ] Paste one sample emitted line (synthetic, no secret) into the journal as the reference
      format for later tasks.
- [ ] Journal entry written.

## 6. Stop and hand off

- **BLOCKED if:** the settings do not expose a data root, which would mean a contract change.
  Report it rather than adding a field silently.
- **Record:** M0 `PROGRESS.md`, `STATUS.md`, and the journal. Re-run G0 and append the result to
  `GATE.md` if M0-T04 is also done.
- **Next:** M1-T05.
