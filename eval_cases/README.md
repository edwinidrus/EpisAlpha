# Evaluation cases

`manifests/` holds the three **real** demo cases. `development/` holds **synthetic** adversarial
variants. The two are kept in separate directories so a synthetic case can never be mistaken for
evidence about a real company.

## Status of the real cases

All three are marked `PROVISIONAL`. Their `intended_case` values come from public reporting about
2026 guidance changes, **not** from reading the filings. The M2-T04 owner checkpoint requires
manually inspecting the key quotations before any of them is treated as settled.

If a filing turns out not to support its intended case, reassign the case. Do not reshape the
question to preserve the intended outcome — that would be fitting the test to the answer.

## Validation and holdout labels

Per plan section 4.1, validation and holdout labels live **outside** this directory, under an
evaluator-only path. They are never placed where the Hermes snapshot or a candidate optimizer
can reach them.
