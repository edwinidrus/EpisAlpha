# M8-T05 — Trace-grounded improvement backlog (A14)

| Field | Value |
|---|---|
| Status | TODO |
| Depends on | G7, M0-T07. It may run **before** M8-T01, because its report seeds proposals. |
| Phase constitution | [../CONSTITUTION.md](../CONSTITUTION.md) (inherits [global](../../CONSTITUTION.md), §VII and §VIII) |
| Plan source | amendment A14 |
| Journal | `tasks/M8-T05-trace-backlog.journal.md` |

## 0. Context to load

Load these and nothing else:
- `implementation/CONSTITUTION.md`, §VII (articles 27–29: span table, never canonical, content
  policy) and §VIII
- `implementation/M8-learning/CONSTITUTION.md`, articles 2, 3 and 11
- `implementation/M6-evaluation/CONSTITUTION.md`, article 2 (labels are sealed)
- `src/episalpha/observability.py` (M0-T06) and `docs/implementation/phoenix.md` (M0-T07)
- `src/episalpha/learning/skills.py` (M8-T01), if it already exists, for linking provenance

Phoenix export facts (docs, 2026-10-10): `client.spans.get_spans_dataframe(project_identifier=...)`
and `client.spans.get_span_annotations_dataframe(...)`, joined by span ID. There is no single
call that returns both.

## 1. Plan

- **Goal:** turn what the whole system actually did into a ranked, evidence-linked list of where
  research fails and what it costs. The inputs are Phoenix traces, together with the owner's
  span annotations ("bad citation", "missed contradiction", "good", and so on). The output
  grounds M8 skill proposals and M6 hypotheses in observed behaviour, not guesses.
- **Files:**
  - `src/episalpha/learning/diagnostics.py` (new)
  - `src/episalpha/cli.py`, adding `episalpha diagnose pull` and `episalpha diagnose report`
  - Focused test: `tests/learning/test_diagnostics.py`
- **`diagnose pull --since <date>`:**
  - It reads spans and annotations from the local Phoenix.
  - Preferred method: Phoenix's HTTP API through stdlib `urllib`, if the API exposes spans and
    annotations. Otherwise use `arize-phoenix-client` in an **optional** `diagnose` dependency
    group, so the core install is untouched.
  - It writes a snapshot `.episalpha/diagnostics/<timestamp>/spans.jsonl` and
    `annotations.jsonl`, plus a `manifest.json` with SHA-256 hashes, the Phoenix version, the
    project, the time range and the counts.
  - It reads with the loopback check, and it never deletes from Phoenix.
- **`diagnose report <snapshot>`:** produces a deterministic Markdown and JSON report.
  - **Failure clusters** are keyed by (span name, stage, tool, `error_code` /
    `episalpha.outcome`, failed validation-check ID, model, `served_by`). Each cluster records
    its count, its share of runs, example trace IDs (up to 5), mean tokens and latency, and
    requests spent.
  - **Annotation clusters** group the owner's annotation labels by span name and stage, with
    trace IDs.
  - **Cost hotspots:** the top spans by tokens and latency.
  - **Non-AI failures** are listed in their own section: connectors (`SOURCE_FAILED` rates),
    sandbox (timeouts, cancels), validation (most frequent failing checks), repair success rate.
  - **Seeds:** each cluster becomes a suggested *improvement target*, with a pointer to its
    evidence (trace IDs). It is not a decision. For example: "numeric-correctness failures in
    `stage.synthesizing` → candidate skill target".
- **Linking (optional, if M8-T01 exists):** a skill proposal or M6 hypothesis may cite the
  `cluster_id` and snapshot hash as provenance.
- **Never:**
  - Phoenix annotations are never evaluation labels, which stay sealed (M6 article 2).
  - The report never auto-creates a proposal or promotes anything.
  - No application logic reads Phoenix at run time.
  - Label content is never sent into Phoenix.

## 2. Verify (before building)

- [ ] Phoenix (M0-T07) is running, with at least one real trace. Verify which export API this
      Phoenix version offers, and journal the endpoint or client calls actually used.
- [ ] If the client package is needed, add it only to an optional `diagnose` group, and confirm
      that `uv sync` without that group still passes the four checks.
- [ ] Baseline: the four checks and `diagnose.py` are green.
- [ ] **Red first.** Write `tests/learning/test_diagnostics.py`, using fixture span and
      annotation JSON lines with no network. Cover:
  - Clustering is deterministic: the same snapshot gives a byte-identical report.
  - Non-AI failures (connector `SOURCE_FAILED`, sandbox timeout) appear in their own section.
  - The annotation join is by span ID.
  - A secret placed in a fixture attribute is redacted in the report.
  - The pull refuses a non-loopback endpoint.
  - The snapshot manifest hashes match the files.

## 3. Build

1. Write the snapshot writer and the manifest.
2. Write the pull adapter. It is thin and the only Phoenix-specific code.
3. Write the clustering and report rendering, both pure.
4. Write the CLI commands.

## 4. Test

```bash
uv run pytest -q tests/learning/test_diagnostics.py
uv run episalpha diagnose pull --since 2026-10-01 && uv run episalpha diagnose report <snapshot>
uv run ruff check . && uv run ruff format --check . && uv run mypy src/episalpha && uv run pytest -q -m "not live"
```

Acceptance:
- [ ] One real snapshot is pulled, and its report lists AI and non-AI failure clusters with
      trace IDs.
- [ ] Reports are deterministic.
- [ ] No secret or label content appears.
- [ ] The core install has no new mandatory dependency.

## 5. Diagnose

- [ ] `diagnose.py`: no regression.
- [ ] Journal: the top 3 clusters from the real report, and which became M8 or M6 targets.

## 6. Stop and hand off

- **BLOCKED if:** the Phoenix version exposes no export path without a heavy dependency, and the
  owner declines the optional group.
- **Record:** M8 `PROGRESS.md`, `STATUS.md`, and the journal.
- **Next:** M8-T01. Alternatively, feed the report into an existing M8 or M6 cycle.
