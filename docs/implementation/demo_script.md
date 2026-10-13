# EpisAlpha six-minute walkthrough (M5-T04)

The owner's demo of the browser workbench. Every run below is a **[FIXTURE]** from the fake
runtime: scripted output over the synthetic corpus, not research. The experiment segment is
reserved for M6 and is step 7 below (added by M6-T04).

## Before you start (not timed)

```bash
uv run episalpha demo seed
uv run episalpha research run --case conflicting        # a completed [FIXTURE] run
uv run streamlit run apps/streamlit_app.py              # http://127.0.0.1:8501
```

Docker: `docker compose up -d`, then `docker compose run --rm cli demo seed` and
`docker compose run --rm cli research run --case conflicting`.

## Steps

| # | Time | Do | Expected screen |
|---:|---:|---|---|
| 1 | 0:00–1:00 | **Research** tab. Pick a demo case in the form (or keep the run just created). The newest run is preselected in **Run**. | `Completed` badge; the yellow **[FIXTURE]** label; the retrospective notice; model, served by, harness (`none (fixture)`), elapsed, usage with unknown tokens and cost; "Saved replay: N artifacts verified"; the stage table. |
| 2 | 1:00–2:00 | Scroll to **Thesis**. | Stance badge; each section's assertions as plain text, each with chips `record · epistemic status · review status`; `missing:` lines and `next inquiry:` at the end. |
| 3 | 2:00–3:00 | **Evidence** tab (click 1). The first assertion is open. Open **Assertion** (click 2) and pick *interpretation* (click 3). | The claim with `reported` and `unreviewed` badges; the six clocks (cutoff, run executed, claim created, published, publicly available with its basis, captured); the span locator; the original passage as plain text: "Management expects demand to soften during the first half." |
| 4 | 3:00–4:00 | Same screen: read `contradicts:` / `contradicted by:` and the hypothesis block. | The critic's contradiction (`c2` contradicts `c1`); the hypothesis' mechanism, falsification condition, supporting and opposing claims. |
| 5 | 4:00–5:00 | **Knowledge** tab. Read the relation table, then the graph. Click **Export to Obsidian vault**. | `CONTRADICTS` row with origin `recorded`; implied edges named by their origin field; the graph (≤ 50 nodes) around the thesis; "Exported N files to `generated/<run_id>`". |
| 6 | 5:00–6:00 | Back on **Research**: the saved-replay caption. In a terminal: `uv run episalpha replay <run_id>`. | The same thesis, read from hash-verified artifacts with zero model or network calls. |
| 7 | 6:00–7:30 | Terminal: `uv run episalpha experiment compare --campaign demo-v1 --runtime fake`. Then the **Experiments** tab. | The disclaimer and the [FIXTURE] label; the decision badge (today: *Challenger rejected · baseline retained*, a complete valid result); one card per gate, PASS or FAIL with its evidence; every trial, failed and interrupted ones included; aggregates as numerator/denominator; tokens and cost `unknown`; the candidate's one-line patch; a Markdown download (also written to `<data_root>/campaigns/<id>/report.md`). |

Assertion to original passage: **3 clicks** (step 3). For the first assertion, 1 click.

Step 7 needs `[evaluation] labels_dir` in the settings, pointing outside the repository at the
owner-reviewed labels (see `eval_cases/campaigns/demo-v1/README.md`). With only the four
development cases, gate 0 fails ("0 validation cases") and the baseline is retained: an honest
result, not a broken demo.

## Manual Obsidian check (owner)

Open `<data_root>/exports/vault` as a vault in Obsidian. Open
`generated/<run_id>/thesis/<run_id>.thesis.md` and follow a claim link to its span and document.
Record the date, the Obsidian version and the result in the M5-T04 journal and in G5.
