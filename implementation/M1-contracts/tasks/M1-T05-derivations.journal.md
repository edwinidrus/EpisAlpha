# M1-T05 journal

## Attempt 1 — 2026-10-10 22:55 UTC — claude-opus-5-5
- Hypothesis: a pure-Decimal registry plus one validator check closes the A8 gap (the validator
  checked that derivation inputs existed but never recomputed the value).
- Verify:
  - `grep -n "class NumericFact\|class Derivation\|numeric_fact\|def check_claim_references\|def validate" ...`
    -> `knowledge.py:265 class NumericFact`, `:283 class Derivation`, `:305 numeric_fact:
    NumericFact | None = None`, `validation.py:121 def check_claim_references`, `:257 def
    validate(`.
  - `DecimalString = Annotated[Decimal, BeforeValidator(_decimal_string)]` (`knowledge.py:159`):
    values arrive as `Decimal`.
  - Baseline: four checks green, 341 passed.
  - Red first: the test file was written before the module, but I did not run it red before
    writing `derivations.py` (written in the next step). Recorded honestly; the first run was
    3 failed / 46 passed, all three test-side bugs (identifiers `'a'`/`'b'` shorter than the
    3-character identifier rule), fixed in the test.
- Did:
  - `src/episalpha/research/derivations.py` (new): `DerivationError`, `Method`, `REGISTRY`
    (`MappingProxyType`; difference, pct_change, ratio, margin, range_midpoint,
    guidance_revision, all version "1"), `lookup`, `recompute`, `matches`. One fixed `Context`
    (prec 34, ROUND_HALF_EVEN, traps DivisionByZero/InvalidOperation).
  - `src/episalpha/research/validation.py`: `check_derivations`, wired immediately after
    `check_claim_references`; skips claims whose references check failed.
  - `tests/research/test_derivations.py`: 29 tests.
- Ran:
  - `uv run pytest -q tests/research` -> `49 passed`
  - `uv run pytest -q tests/contracts tests/evidence/test_temporal.py tests/research/test_validation.py tests/research/test_derivations.py`
    -> `212 passed`
  - Four checks: All checks passed; 41 files already formatted; no issues in 22 source files;
    `370 passed, 3 deselected` (341 + 29).
  - `git diff --stat src/episalpha/contracts tests/research/test_validation.py` -> empty (schema
    and existing tests unchanged).
- Worked example (white-box reference):
  - Inputs, in order: Q3 revenue `400.00 EUR` (2025-07-01..2025-09-30), Q4 revenue `420.92 EUR`
    (2025-10-01..2025-12-31), both `IFRS consolidated`.
  - Method `pct_change@1`: (new − old) / old = (420.92 − 400.00) / 400.00 = 20.92 / 400.00 =
    `0.0523` exactly; unit `ratio`.
  - Claimed `0.0523` (exponent −4): computed quantized to 4 places, ROUND_HALF_EVEN -> `0.0523`
    -> match. A claimed `0.06` quantizes the computation to `0.05` -> mismatch, rejected with
    "claims 0.06 but pct_change@1 recomputed 0.0523 ratio".
  - Validator output on the serialized example: `('claim.synthetic-claim.revenue-growth.derivation', True, '')`.
- Outcome: PASS
