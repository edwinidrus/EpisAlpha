# M7-T02 journal — Demo packaging and smoke command

## Attempt 1 — 2026-10-13 — claude-opus-5-5
- Verify: M7-T01 green (729). Red first: `uv run pytest -q tests/integration/test_smoke_script.py`
  -> `2 failed` (the script did not exist).
- Did:
  - `scripts/demo_smoke.py` (new, stdlib + subprocess through the CLI): temporary data root and
    settings; seed; three fake cases; replay of each with every non-loopback connect and lookup
    refused (a small bootstrap patches `socket` before the CLI runs); Obsidian export plus a scan
    that every `[[link]]` resolves; `experiment compare --runtime fake` (development label drafts
    copied into a sealed directory outside both roots); backup of DB (SQLite backup API), objects
    and runs as one unit with a hash manifest; restore refuses the unit on any mismatch,
    re-hashes after copying, and a replay runs from the restored copy; prints locations, the
    warm replay time and the total. `--inject-failure` edits a saved artifact first.
  - `tests/integration/test_smoke_script.py` (2): PASS path with every step and location, the
    user's `.episalpha/app.sqlite3` untouched, temporary state under pytest's tmp (TMPDIR);
    injected failure -> non-zero and `INTEGRITY_ERROR`.
  - `README.md`: clean-checkout quick start, workbench on your own data root, live-run note with
    the free-tier numbers, where logs and diagnostics live; status line and table list updated.
  - `config/demo.example.toml`: `[evaluation]` (commented `labels_dir`), `max_contradiction_queries`,
    commented `campaign_requests_per_day` with the owner-decision note.
  - `docs/implementation/demo_acceptance.md`: smoke transcript, performance measurement, row
    status (offline vs live/manual), plan 15.1 checklist.
- Ran:
  - `uv run python scripts/demo_smoke.py` -> `smoke: PASS`, `replay after warm-up: 0.30 s`,
    `total: 4.7 s`.
  - `uv run pytest -q tests/integration/test_smoke_script.py` -> `2 passed`.
  - Clean-copy rehearsal (tracked + new files copied to an empty directory; nothing is committed
    yet, so a literal `git clone` would not include this work): no `.episalpha`, no `.env`,
    credentials unset -> `uv sync --all-groups`, `uv run python scripts/demo_smoke.py` ->
    `smoke: PASS`, `replay after warm-up: 0.28 s`, `total: 4.7 s`.
  - Four checks green; `diagnose.py` -> `PASS | tests {'passed': 731, ...} | regressions 0 |
    orphans 0`.
- Performance target: saved corpus opens in ≤ 5 s after warm-up -> measured 0.28–0.30 s.
- Outcome: PASS.
