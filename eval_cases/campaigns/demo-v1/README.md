# Campaign `demo-v1` cases (M6-T01)

`cases/` holds the case inputs only. Labels never live in this repository: the evaluator reads
them from `evaluation.labels_dir` in settings, which must be outside the project and data roots
(M6 article 2). `load_labels` refuses any other location.

## What exists

Four **development** cases over the SYNTHETIC demo corpus (one document, two passages, family
`synthetic-release-family`). They exercise the machinery with the fake runtime; they say nothing
about any real company.

| Case | Type | Labels draft |
|---|---|---|
| `dev-synthetic-q4-revenue` | extraction | revenue fact, value and unit |
| `dev-synthetic-revenue-units` | numeric_units_periods | same fact; the question asks for unit and period |
| `dev-synthetic-demand-vs-revenue` | contradiction | two facts and the demand-vs-revenue contradiction |
| `dev-synthetic-order-book` | missing_evidence | abstain (the corpus has no order-book figure) |

Label drafts for these four are in `docs/implementation/m6-label-drafts/development/`,
`reviewed_by: null`. Development labels are visible by design (plan 12.1), so a draft in the
repository leaks nothing.

## What the owner must supply (plan 12.1 asks for 12 / 6 / 6)

1. **Review the development drafts**, set `reviewed_by` and `reviewed_at`, and copy them into
   `labels_dir`. Only then are they frozen evaluator inputs.
2. **Eight more development cases**, and **6 validation + 6 final-check cases**, each from a
   source family used in no other partition. Required types still uncovered:
   `source_attribution`, `duplicate_lineage`, `future_evidence`, `injected_instruction`. They need
   evidence beyond the one synthetic document, ideally the real filings of the G2 checkpoint.
3. Write validation and final-check labels **directly into `labels_dir`**, never into this
   repository: a candidate author can read the repository.
4. Set `[evaluation] labels_dir = "/absolute/path/outside/the/repo"` in `config/demo.toml`.
