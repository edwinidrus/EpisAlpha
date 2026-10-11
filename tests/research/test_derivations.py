"""M1-T05 — derived numbers are recomputed, never asserted (amendment A8)."""

from __future__ import annotations

import ast
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fixtures.synthetic_knowledge import (
    DEMAND_SPAN,
    DOCUMENT_TEXT,
    REVENUE_SPAN,
    SYNTHETIC_DOCUMENT,
    SYNTHETIC_ENTITY,
    SYNTHETIC_INSTRUMENT,
)

from episalpha.contracts.errors import ErrorCode
from episalpha.contracts.knowledge import Claim, Derivation, EpistemicStatus, NumericFact
from episalpha.research import derivations
from episalpha.research.derivations import REGISTRY, DerivationError, matches, recompute
from episalpha.research.validation import RecordSet, failed_checks, validate

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
Q3 = (datetime(2025, 7, 1, tzinfo=UTC), datetime(2025, 9, 30, tzinfo=UTC))
Q4 = (datetime(2025, 10, 1, tzinfo=UTC), datetime(2025, 12, 31, tzinfo=UTC))
FY26 = (datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 12, 31, tzinfo=UTC))


def fact(
    value: str,
    unit: str = "EUR",
    period: tuple[datetime, datetime] = Q4,
    basis: str = "IFRS consolidated",
    metric: str = "revenue",
) -> NumericFact:
    return NumericFact(
        metric=metric,
        value=value,
        unit=unit,
        period_start=period[0],
        period_end=period[1],
        accounting_basis=basis,
        source_context="synthetic",
    )


def reported(claim_id: str, numeric: NumericFact | None) -> Claim:
    return Claim(
        claim_id=claim_id,
        statement=f"Synthetic figure {claim_id}.",
        subject_ids=("synthetic-issuer.eq",),
        attribution="Synthetic release",
        epistemic_status=EpistemicStatus.REPORTED,
        span_ids=("synthetic-span.revenue",),
        numeric_fact=numeric,
        created_at=NOW,
    )


def derived(
    method: str,
    inputs: tuple[str, ...],
    numeric: NumericFact | None,
    version: str = "1",
    claim_id: str = "claim.derived",
) -> Claim:
    return Claim(
        claim_id=claim_id,
        statement="A derived synthetic figure.",
        subject_ids=("synthetic-issuer.eq",),
        attribution="EpisAlpha derivation",
        epistemic_status=EpistemicStatus.DERIVED,
        derivation=Derivation(method=method, method_version=version, input_claim_ids=inputs),
        numeric_fact=numeric,
        created_at=NOW,
    )


def records(*claims: Claim) -> RecordSet:
    return RecordSet(
        entities=[SYNTHETIC_ENTITY],
        instruments=[SYNTHETIC_INSTRUMENT],
        documents=[SYNTHETIC_DOCUMENT],
        spans=[REVENUE_SPAN, DEMAND_SPAN],
        claims=list(claims),
        document_texts={"synthetic-doc.v1": DOCUMENT_TEXT},
    )


def derivation_failures(*claims: Claim) -> list[str]:
    report = validate(records(*claims), run_id="run.0001")
    return [f"{c.check}: {c.detail}" for c in failed_checks(report)]


def check(method: str, facts: list[NumericFact], claimed: NumericFact | None) -> list[str]:
    inputs = tuple(f"claim.in{index}" for index in range(len(facts)))
    claims = [reported(cid, item) for cid, item in zip(inputs, facts, strict=True)]
    return derivation_failures(*claims, derived(method, inputs, claimed))


# --- each method, correct value ------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "facts", "claimed"),
    [
        ("difference", [fact("400.0"), fact("412.5")], fact("12.5")),
        (
            "pct_change",
            [fact("400.00", period=Q3), fact("420.92", period=Q4)],
            fact("0.0523", unit="ratio"),
        ),
        (
            "ratio",
            [fact("150.0", metric="gross_profit"), fact("412.0")],
            fact("0.3641", unit="ratio"),
        ),
        (
            "margin",
            [fact("41.2", metric="operating_income"), fact("412.0")],
            fact("0.100", unit="ratio"),
        ),
        (
            "range_midpoint",
            [fact("1.90", unit="USD", period=FY26), fact("2.00", unit="USD", period=FY26)],
            fact("1.95", unit="USD", period=FY26),
        ),
        (
            "guidance_revision",
            [
                fact("2.13", unit="USD", period=FY26),
                fact("2.23", unit="USD", period=FY26),
                fact("1.90", unit="USD", period=FY26),
                fact("2.00", unit="USD", period=FY26),
            ],
            fact("-0.23", unit="USD", period=FY26),
        ),
    ],
)
def test_each_method_accepts_its_correct_value(
    method: str, facts: list[NumericFact], claimed: NumericFact
) -> None:
    assert check(method, facts, claimed) == []


def test_every_method_is_registered_at_version_1() -> None:
    assert sorted(REGISTRY) == [
        ("difference", "1"),
        ("guidance_revision", "1"),
        ("margin", "1"),
        ("pct_change", "1"),
        ("range_midpoint", "1"),
        ("ratio", "1"),
    ]


# --- value and rounding --------------------------------------------------------------------


def test_a_wrong_value_is_rejected() -> None:
    failures = check(
        "pct_change",
        [fact("400.00", period=Q3), fact("420.92", period=Q4)],
        fact("0.06", unit="ratio"),
    )
    assert len(failures) == 1
    assert "claim.derived.derivation" in failures[0]
    assert "recomputed" in failures[0]


def test_rounding_follows_the_claimed_precision() -> None:
    assert matches(Decimal("0.0523"), Decimal("0.052347"))
    assert not matches(Decimal("0.0524"), Decimal("0.052347"))
    assert matches(Decimal("0.0524"), Decimal("0.05235"))  # half-even rounds 0.05235 to 0.0524
    assert matches(Decimal("12"), Decimal("12.4"))


def test_worked_example_is_exact() -> None:
    value, unit = recompute(
        Derivation(method="pct_change", method_version="1", input_claim_ids=("claim.a", "claim.b")),
        [fact("400.00", period=Q3), fact("420.92", period=Q4)],
    )
    assert (value, unit) == (Decimal("0.0523"), "ratio")


# --- registry lookups ----------------------------------------------------------------------


def test_unknown_method_is_a_typed_error() -> None:
    with pytest.raises(DerivationError) as raised:
        recompute(
            Derivation(method="cagr", method_version="1", input_claim_ids=("claim.a",)), [fact("1")]
        )
    assert raised.value.code is ErrorCode.INVALID_OUTPUT
    assert "unknown method 'cagr'" in str(raised.value)


def test_unknown_version_is_rejected() -> None:
    failures = check("difference", [fact("1"), fact("2")], fact("1"))
    assert failures == []
    inputs = ("claim.in0", "claim.in1")
    claims = [reported("claim.in0", fact("1")), reported("claim.in1", fact("2"))]
    failures = derivation_failures(*claims, derived("difference", inputs, fact("1"), version="2"))
    assert len(failures) == 1
    assert "unknown version '2' of method 'difference'" in failures[0]


def test_wrong_arity_is_rejected() -> None:
    failures = check("difference", [fact("1"), fact("2"), fact("3")], fact("1"))
    assert len(failures) == 1
    assert "takes 2 inputs, got 3" in failures[0]


# --- compatibility -------------------------------------------------------------------------


def test_unit_mismatch_is_rejected() -> None:
    failures = check("difference", [fact("1", unit="EUR"), fact("2", unit="USD")], fact("1"))
    assert "units differ" in failures[0]


def test_accounting_basis_mismatch_is_rejected() -> None:
    failures = check(
        "pct_change",
        [fact("100", period=Q3, basis="IFRS"), fact("110", basis="US GAAP")],
        fact("0.1", unit="ratio"),
    )
    assert "accounting bases differ" in failures[0]


@pytest.mark.parametrize(
    ("method", "claimed"),
    [
        ("ratio", fact("0.5", unit="ratio")),
        ("margin", fact("0.5", unit="ratio")),
        ("range_midpoint", fact("1.5")),
    ],
)
def test_period_mismatch_is_rejected(method: str, claimed: NumericFact) -> None:
    failures = check(method, [fact("1", period=Q3), fact("2", period=Q4)], claimed)
    assert "periods differ" in failures[0]


def test_guidance_revision_needs_one_target_period() -> None:
    failures = check(
        "guidance_revision",
        [fact("1"), fact("2"), fact("1", period=FY26), fact("2", period=FY26)],
        fact("0"),
    )
    assert "periods differ" in failures[0]


def test_inverted_range_is_rejected() -> None:
    failures = check("range_midpoint", [fact("2.00"), fact("1.90")], fact("1.95"))
    assert "low 2.00 exceeds high 1.90" in failures[0]


@pytest.mark.parametrize(
    ("method", "facts"),
    [
        ("pct_change", [fact("0", period=Q3), fact("5")]),
        ("ratio", [fact("5"), fact("0")]),
        ("margin", [fact("5"), fact("0.00")]),
    ],
)
def test_division_by_zero_is_a_failed_check_never_zero(
    method: str, facts: list[NumericFact]
) -> None:
    failures = check(method, facts, fact("0", unit="ratio"))
    assert len(failures) == 1
    assert "division by zero" in failures[0]


# --- missing numbers -----------------------------------------------------------------------


def test_derived_claim_without_numeric_fact_is_rejected() -> None:
    failures = check("difference", [fact("1"), fact("2")], None)
    assert "derived numeric method requires numeric_fact" in failures[0]


def test_input_without_numeric_fact_is_rejected() -> None:
    claims = [reported("claim.in0", fact("1")), reported("claim.in1", None)]
    failures = derivation_failures(
        *claims, derived("difference", ("claim.in0", "claim.in1"), fact("1"))
    )
    assert "input claim 'claim.in1' has no numeric_fact" in failures[0]


def test_claimed_unit_must_equal_the_output_unit() -> None:
    failures = check(
        "pct_change",
        [fact("400.00", period=Q3), fact("420.92", period=Q4)],
        fact("5.23", unit="percent"),
    )
    assert "unit 'percent' but method pct_change@1 produces 'ratio'" in failures[0]


def test_a_missing_input_is_reported_once_by_the_references_check() -> None:
    failures = derivation_failures(
        reported("claim.in0", fact("1")),
        derived("difference", ("claim.in0", "claim.ghost"), fact("1")),
    )
    assert len(failures) == 1
    assert "claim.derived.references" in failures[0]


def test_derivations_module_contains_no_float() -> None:
    source = Path(derivations.__file__).read_text()
    tree = ast.parse(source)
    floats = [
        node
        for node in ast.walk(tree)
        if (isinstance(node, ast.Name) and node.id == "float")
        or (isinstance(node, ast.Constant) and isinstance(node.value, float))
    ]
    assert floats == []


def test_recompute_reads_inputs_in_order() -> None:
    forward: dict[str, Any] = {"method": "difference", "method_version": "1"}
    a_then_b = recompute(
        Derivation(**forward, input_claim_ids=("claim.a", "claim.b")), [fact("1"), fact("3")]
    )
    b_then_a = recompute(
        Derivation(**forward, input_claim_ids=("claim.b", "claim.a")), [fact("3"), fact("1")]
    )
    assert a_then_b == (Decimal("2"), "EUR")
    assert b_then_a == (Decimal("-2"), "EUR")
