# M4-T02 journal

## Attempt 1 — 2026-10-11 06:55 UTC — claude-opus-5-5
- Verify:
  - Runner API from M4-T01: `admit`, `claim`, `request_cancel`, `ResearchRunner.execute`.
  - Case manifests carry `question` and `research_cutoff`
    (`grep -n "question\|cutoff" eval_cases/manifests/*.json`: all three).
  - Baseline: four checks green, 523 passed.
  - Red first: **not honoured**. `services.py` and `cli.py` were written before
    `test_cli_research.py`. The tests then covered the pack's list and passed (21 passed).
- Decisions:
  - **No logic in the CLI** (M4 article 8). A new `src/episalpha/research/services.py` holds
    the workbench, case registry, demo seed, evidence loaders, request construction,
    submission, execution and runtime construction; the browser (M5) reuses it. This is the
    task's second implementation file.
  - **Three evidence worlds, never mixed.** Fake runs use the synthetic corpus
    (`eval_cases/demo/synthetic_corpus.json`, generated from the test fixture with real content
    hashes) under the synthetic issuer, never under a real ticker; they keep the case's question
    and cutoff and print `[FIXTURE]`. Hermes case runs freeze the real filings ingested for the
    case's CIK. With none ingested yet they abstain at freeze, with no model call (tested).
    Snapshot reruns rebuild evidence from the snapshot's documents, with texts from the content
    store.
  - The runner now stores each frozen document's text in the content store under its
    `parsed_text_hash` (warning on mismatch), so snapshots can be re-read.
  - The idempotency key hashes the source, instrument, question, cutoff, runtime mode and
    harness, so fake and real runs never collide and a resubmission returns its run.
  - `submission.json` beside the run artifacts records how to execute an admitted run (evidence
    kind, case, fake scenario), so `research execute RUN_ID` never re-admits. The fake scenario
    can be overridden with `EPISALPHA_FAKE_SCENARIO` (test and demo use; the CLI interface is
    unchanged).
  - `research run` opens a `cli.research.run` span for admission only; `research.run` stays
    the root of the run's own trace.
  - The Hermes runtime uses the sandbox worker when the pinned image and Docker exist;
    `EPISALPHA_WORKER=local` selects the venv worker; otherwise it refuses (exit 2).
  - `replay` exits 2 ("not implemented yet") until M4-T03.
- Did: `src/episalpha/cli.py`, `src/episalpha/research/services.py`,
  `eval_cases/demo/synthetic_corpus.json`, `src/episalpha/research/runner.py` (text storage),
  `tests/integration/test_cli_research.py` (21 tests).
- Ran: `uv run pytest -q tests/integration/test_cli_research.py` -> `21 passed`; four checks
  green, `pytest -m "not live"` -> see PROGRESS.
- Real CLI transcripts (fake runtime, demo config, 2026-10-11):
```
seeded: entities 4, instruments 4, documents 1, spans 2
database: /home/edwinidrus/hobbys/EpisAlpha/.episalpha/app.sqlite3
exit=0
seeded: entities 4, instruments 4, documents 1, spans 2
database: /home/edwinidrus/hobbys/EpisAlpha/.episalpha/app.sqlite3
exit=0
[FIXTURE] fake runtime: scripted fixture output, not research
run_id: run-15b0260c2fac
state: RESEARCH_COMPLETED
reason: research completed and validated
notice: Retrospective research; model training knowledge may include later events.
usage: model requests 6, tool calls 4, tokens (prompt/completion) unknown, cost unknown
thesis: run-15b0260c2fac.thesis
artifacts: /home/edwinidrus/hobbys/EpisAlpha/.episalpha/runs/run-15b0260c2fac
trace: ce97682657ae2a393377aca9ed0652f1
exit=0
[FIXTURE] fake runtime: scripted fixture output, not research
run_id: run-35b280fd60e3
state: REJECTED
reason: researching output invalid after one repair: claim.run-35b280fd60e3.c1.references: cites unknown spans ['synthetic-span.fabricated']
error_code: INVALID_OUTPUT
notice: Retrospective research; model training knowledge may include later events.
usage: model requests 4, tool calls 4, tokens (prompt/completion) unknown, cost unknown
artifacts: /home/edwinidrus/hobbys/EpisAlpha/.episalpha/runs/run-35b280fd60e3
trace: 86cf89e9d4092878fd026f1c07e37335
exit=3
[FIXTURE] fake runtime: scripted fixture output, not research
run_id: run-4e8fe146a00c
state: ABSTAINED
reason: the synthesizer abstained: the validated evidence does not answer the question. Next inquiry: Check the next quarterly filing for order-book disclosure.
notice: Retrospective research; model training knowledge may include later events.
usage: model requests 6, tool calls 4, tokens (prompt/completion) unknown, cost unknown
thesis: run-4e8fe146a00c.thesis
artifacts: /home/edwinidrus/hobbys/EpisAlpha/.episalpha/runs/run-4e8fe146a00c
trace: a4aaa2d39bedbe82e935c76edb8ed4f4
exit=5
```
- Outcome: PASS
