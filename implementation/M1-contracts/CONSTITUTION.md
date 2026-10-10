# M1 constitution: canonical contracts and epistemic invariants

Inherits [../CONSTITUTION.md](../CONSTITUTION.md). The articles below add to it and never relax it.

1. **Schema version is frozen at `1`.**
   - Any change to a field, enum or contract shape needs an explicit compatibility decision,
     recorded in `PROGRESS.md`.
   - Additive and backward-compatible changes still get that note.
2. **The vocabulary is closed.** Values come from the plan §3.3 enums. No string-typed status,
   predicate or stance bypasses its enum.
3. **Contracts reject; they do not repair.** Invalid input raises a validation error with an
   actionable message. Nothing is coerced, defaulted or guessed.
4. **The validator is pure and deterministic.**
   - `research/validation.py` and `research/derivations.py` do no I/O, read no clock and make no
     network calls.
   - The same `RecordSet` always gives the same `ValidationReport`.
5. **Quotation matching is not entailment.** A string match never sets `supported`. Only a
   `SemanticAssessment` does.
6. **Derivations are recomputed (A8).**
   - A derived number is accepted only when a registered `method`@`method_version` reproduces it
     from the input claims' `NumericFact`s.
   - Methods are pure `Decimal` functions.
   - A published method version is immutable. A change means a new version.
   - No floats anywhere: no `float()` and no float literals in a computation path.
7. **Existing tests are a contract.** M1-T05 may add checks; it may not edit the M1-T04 tests to
   accommodate them. If an existing test breaks, the new check is wrong.
