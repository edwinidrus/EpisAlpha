# M1-T05 — Derivation registry and recomputation (A8)

| Field | Value |
|---|---|
| Status | TODO |
| Depends on | G1 |
| Phase constitution | [../CONSTITUTION.md](../CONSTITUTION.md) (inherits [global](../../CONSTITUTION.md)) |
| Plan source | plan §3.4 "Numbers are reported or recomputed", §3.6 step 7, M1-T05 card; amendment A8 |
| Journal | `tasks/M1-T05-derivations.journal.md` |

## 0. Context to load

Load these and nothing else:
- `implementation/CONSTITUTION.md`
- `implementation/M1-contracts/CONSTITUTION.md`
- [../PLAN.md](../PLAN.md), the interface table
- `src/episalpha/contracts/knowledge.py:265-330` (`NumericFact`, `Derivation`, `Claim`)
- `src/episalpha/research/validation.py`, the whole file (about 310 lines)
- `tests/research/test_validation.py:1-60` and `:230-275` (fixtures, `derived()`, the two
  existing derivation tests)
- `tests/fixtures/synthetic_knowledge.py`

> Every number a `ThesisAssertion` relies on comes from a `NumericFact` on either a `reported`
> claim with a cited span, or a `derived` claim whose `Derivation` names a registered
> `method`@`method_version` and whose value the validator recomputes from the input claims'
> `NumericFact`s. A mismatch, an unknown method, or incompatible input units/periods fails
> validation. (plan §3.4, A8)

## 1. Plan

- **Goal:** `validate()` rejects any derived claim whose value a registered method does not
  reproduce. Before this task, it only checked that the inputs existed.
- **Files:**
  - `src/episalpha/research/derivations.py` (new)
  - `src/episalpha/research/validation.py` (add `check_derivations`, wire it into `validate()`)
  - Focused test: `tests/research/test_derivations.py`
- **Produces, in `derivations.py`:**
  - `@dataclass(frozen=True) class Method`, with fields `name`, `version`, `arity` and
    `output_unit_rule`, plus a `compute` callable that takes a tuple of `NumericFact` and returns
    `(Decimal, unit: str)`.
  - `REGISTRY: Mapping[tuple[str, str], Method]`, built once as a `MappingProxyType`.
  - `def recompute(derivation: Derivation, inputs: Sequence[NumericFact]) -> tuple[Decimal, str]`,
    which raises `DerivationError(EpisAlphaError)` with `ErrorCode.INVALID_OUTPUT` on any rule
    break.
  - `def matches(claimed: Decimal, computed: Decimal) -> bool`. The **rounding rule:** quantize
    `computed` to the exponent of `claimed` with `ROUND_HALF_EVEN`, then compare for equality.
    `# ponytail: precision follows the claim's stated digits; add a minimum-precision rule if
    coarse claims become a problem.`
- **Methods, all version `"1"`.** `input_claim_ids` order is significant.

  | Method | Inputs, in order | Result | Unit out | Compatibility rule |
  |---|---|---|---|---|
  | `difference` | (a, b) | b − a | input unit | same unit, same accounting_basis |
  | `pct_change` | (old, new) | (new − old) / old | `ratio` | same unit, same accounting_basis; old ≠ 0 |
  | `ratio` | (num, den) | num / den | `ratio` | same unit, identical period; den ≠ 0 |
  | `margin` | (part, revenue) | part / revenue | `ratio` | same unit, identical period, same accounting_basis; revenue ≠ 0 |
  | `range_midpoint` | (low, high) | (low + high) / 2 | input unit | same unit, identical period; low ≤ high |
  | `guidance_revision` | (prior_low, prior_high, new_low, new_high) | mid(new) − mid(prior) | input unit | all same unit and identical target period; low ≤ high in each pair |

- **`check_derivations(records) -> list[CheckResult]`**, with check name
  `claim.<id>.derivation`:
  - Applies to every claim with `derivation is not None`.
  - Skips claims whose references already failed, so that `check_claim_references` stays the
    single reporter of missing or circular inputs.
  - Fails, each with a specific `detail`, when:
    - the claim has no `numeric_fact` ("derived numeric method requires numeric_fact");
    - an input claim has no `numeric_fact`;
    - the method is unknown, or the version is unknown;
    - the arity is wrong;
    - the inputs are incompatible;
    - a divisor is zero;
    - the claimed unit differs from the output unit;
    - the value does not match.
- **`validate()` wiring:** insert `*check_derivations(records)` **immediately after**
  `*check_claim_references(records)`.
- **Out of scope:**
  - Exposing the registry as a tool (M3-T01).
  - Any new contract field. `SCHEMA_VERSION` stays `1`.
  - Units conversion. Incompatible means fail; nothing is converted.
- **Do not:**
  - Edit existing tests. `test_a_derivation_from_an_unknown_input_is_rejected` and
    `test_a_claim_cannot_derive_from_itself` read `failed_checks(report)[0]`; the wiring order
    plus the skip rule keep them green.
  - Use floats.
  - Read a clock.
  - Log, until M0-T06 exists; and even then, `validation.py` stays pure (constitution article 4).

## 2. Verify (before building)

- [ ] The interfaces exist as stated:
      `grep -n "class NumericFact\|class Derivation\|numeric_fact\|def check_claim_references\|def validate" src/episalpha/contracts/knowledge.py src/episalpha/research/validation.py`.
      Paste the result into the journal.
- [ ] `DecimalString` resolves to `Decimal` (`knowledge.py:159`). Values arrive as `Decimal`.
- [ ] Baseline: the four standard checks are green. Record the count (expect 305 passed).
- [ ] **Red first.** Write `tests/research/test_derivations.py`, reusing
      `fixtures.synthetic_knowledge` and the `base_records` pattern from `test_validation.py`.
      Run it and confirm it fails on the import. Cover:
  - Each method with a correct value: 6 tests.
  - A wrong value is rejected, for example a claimed `0.06` when the true value is `0.0523`.
  - Rounding: a claimed `0.0523` against an exact `0.052347` passes.
  - Unknown method; unknown version; wrong arity.
  - Unit mismatch; accounting-basis mismatch; period mismatch for `ratio`, `margin` and
    `range_midpoint`.
  - Division by zero is a failed check, not a crash, and never `0`.
  - A derived claim without `numeric_fact`; an input without `numeric_fact`.
  - Claimed unit ≠ output unit (for example `percent` for `pct_change`).
  - A missing input is reported only once, by the references check.
  - An AST or grep test that `derivations.py` contains no `float`.

## 3. Build

1. Write `DerivationError` and the compatibility helpers: `_same_unit`, `_same_basis`,
   `_same_period`.
2. Write the six pure compute functions and the `REGISTRY`.
3. Write `recompute` and `matches`.
4. Write `check_derivations`, then wire it into `validate()`.

## 4. Test

```bash
uv run pytest -q tests/research/test_derivations.py tests/research/test_validation.py
uv run ruff check . && uv run ruff format --check . && uv run mypy src/episalpha && uv run pytest -q -m "not live"
```

Acceptance:
- [ ] An unknown method or version fails with a typed error.
- [ ] A recomputed value that differs from `claim.numeric_fact.value` fails.
- [ ] Mismatched units or periods fail.
- [ ] Division by zero is an error, never `0`.
- [ ] No floats anywhere.
- [ ] All existing tests are unchanged and green; the total = previous + new tests.
- [ ] Schema is unchanged (`git diff src/episalpha/contracts` is empty).

## 5. Diagnose

- [ ] `uv run python scripts/diagnose.py`: no regression, and `tests/research` grows by the new
      count.
- [ ] Journal entry written. It includes one worked example (inputs, method, computed value,
      quantized value) as a white-box reference for later reviewers.

## 6. Stop and hand off

- **BLOCKED if:**
  - an existing test fails because of the new check and cannot be fixed inside
    `check_derivations` without editing the test;
  - a contract field is genuinely missing.
- **Record:** M1 `PROGRESS.md`, `STATUS.md`, and the journal. Re-run G1 and append the result to
  `../GATE.md`.
- **Next:** M2-T05.
