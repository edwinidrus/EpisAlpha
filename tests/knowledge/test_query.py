"""M5-T02 — evidence drilldown, relation table and run-scoped graph.

The pure functions are tested over hand-built :class:`RunKnowledge` (SYNTHETIC fixtures, never
evidence about a real issuer). ``load_run`` is tested against real fake-runtime runs in a
``tmp_path`` workbench: every one of them is a labelled fixture, not a live integration.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from fixtures.run_knowledge import (
    DERIVED_CLAIM,
    NOW,
    PRIOR_CLAIM,
    RUN,
    SCRIPT,
    knowledge,
)
from fixtures.synthetic_knowledge import REPORTED_CLAIM, REVENUE_SPAN

from episalpha.contracts.errors import EpisAlphaError
from episalpha.contracts.research import RuntimeMode
from episalpha.knowledge.query import (
    assertion_drilldown,
    load_run,
    local_graph,
    relation_table,
    to_dot,
)
from episalpha.research import services
from episalpha.research.derivations import recompute

REPO = Path(__file__).resolve().parents[2]

# --- drilldown ---------------------------------------------------------------------------------


def test_reported_claim_drills_down_to_its_exact_passage_and_clocks() -> None:
    drill = assertion_drilldown(knowledge(), f"{RUN}.a1")
    (trace,) = drill.claims
    assert trace.claim.claim_id == "synthetic-claim.revenue"
    assert trace.review_status == "unreviewed"
    (passage,) = trace.passages
    assert passage.span.exact_quote == REVENUE_SPAN.exact_quote
    assert passage.document is not None
    assert passage.document.published_at is not None and passage.document.ingested_at
    assert drill.research_cutoff == NOW and drill.executed_at == NOW
    assert trace.chain is None
    assert trace.contradicted_by == ("synthetic-claim.demand",)  # A02: opposing evidence shown


def test_derived_claim_shows_the_chain_recomputed_by_the_registry() -> None:
    drill = assertion_drilldown(knowledge(), f"{RUN}.a2")
    (trace,) = drill.claims
    chain = trace.chain
    assert chain is not None
    expected, unit = recompute(
        DERIVED_CLAIM.derivation,  # type: ignore[arg-type]
        [PRIOR_CLAIM.numeric_fact, REPORTED_CLAIM.numeric_fact],  # type: ignore[list-item]
    )
    assert (chain.method, chain.method_version) == ("pct_change", "1")
    assert chain.value == expected and chain.unit == unit == "ratio"
    assert chain.claimed == Decimal("0.030") and chain.matches is True
    assert [(i.claim_id, i.value, i.unit) for i in chain.inputs] == [
        ("synthetic-claim.prior", Decimal("400000000.00"), "EUR"),
        ("synthetic-claim.revenue", Decimal("412000000.00"), "EUR"),
    ]
    assert chain.inputs[0].period_end == datetime(2025, 12, 31, tzinfo=UTC)
    # A derived claim has no span of its own: its passages are those of its inputs.
    assert {p.span.span_id for p in trace.passages} == {
        "synthetic-span.prior",
        REVENUE_SPAN.span_id,
    }


def test_a_wrong_derived_value_is_flagged_not_hidden() -> None:
    wrong = DERIVED_CLAIM.model_copy(
        update={
            "numeric_fact": DERIVED_CLAIM.numeric_fact.model_copy(  # type: ignore[union-attr]
                update={"value": Decimal("0.500")}
            )
        }
    )
    drill = assertion_drilldown(knowledge(wrong), f"{RUN}.a2")
    assert drill.claims[0].chain is not None and drill.claims[0].chain.matches is False


def test_unsupported_status_and_hypotheses_are_visible() -> None:
    drill = assertion_drilldown(knowledge(), f"{RUN}.a3")
    assert drill.claims[0].review_status == "unsupported"
    (hypothesis,) = drill.hypotheses
    assert hypothesis.review_status == "unreviewed"
    assert hypothesis.hypothesis.opposing_claim_ids == ("synthetic-claim.revenue",)


def test_copied_sources_show_common_lineage() -> None:
    drill = assertion_drilldown(knowledge(), f"{RUN}.a2")
    # A21: two documents, one source family -> one lineage, never two confirmations.
    assert drill.shared_lineage == (
        ("synthetic-release-family", ("synthetic-doc.copy", "synthetic-doc.v1")),
    )


def test_html_in_a_passage_is_returned_as_an_inert_string() -> None:
    drill = assertion_drilldown(knowledge(), f"{RUN}.a2")
    texts = [p.span.exact_quote for p in drill.claims[0].passages]
    assert SCRIPT in texts


def test_an_unknown_assertion_is_refused() -> None:
    with pytest.raises(EpisAlphaError):
        assertion_drilldown(knowledge(), f"{RUN}.missing")


# --- relation table and graph ------------------------------------------------------------------


def rows_by_label(table: list) -> dict[str, set[tuple[str, str]]]:  # type: ignore[type-arg]
    found: dict[str, set[tuple[str, str]]] = {}
    for row in table:
        found.setdefault(row.label, set()).add((row.source_id, row.target_id))
    return found


def test_relation_table_has_recorded_and_record_field_edges() -> None:
    found = rows_by_label(relation_table(knowledge()))
    assert ("synthetic-claim.demand", "synthetic-claim.revenue") in found["CONTRADICTS"]
    assert ("synthetic-span.revenue", "synthetic-claim.revenue") in found["REPORTS"]
    assert ("synthetic-doc.v1", "synthetic-span.revenue") in found["HAS_SPAN"]
    assert ("synthetic-claim.demand", "synthetic-hypothesis.demand") in found["SUPPORTS"]
    assert ("synthetic-claim.revenue", "synthetic-hypothesis.demand") in found["CONTRADICTS"]
    assert ("synthetic-claim.prior", f"{RUN}.d1") in found["derivation input"]
    assert (f"{RUN}.thesis", f"{RUN}.d1") in found["cites"]
    recorded = [row for row in relation_table(knowledge()) if row.relation_id]
    assert [row.relation_id for row in recorded] == [f"{RUN}.r1"]


def test_graph_is_capped_and_flags_truncation() -> None:
    many = [
        REPORTED_CLAIM.model_copy(update={"claim_id": f"synthetic-claim.n{index:02d}"})
        for index in range(60)
    ]
    full = knowledge(*many)
    capped = local_graph(full, limit=50)
    assert len(capped.nodes) == 50 and capped.truncated
    assert capped.nodes[0].node_id == f"{RUN}.thesis"
    ids = {node.node_id for node in capped.nodes}
    assert all(edge.source_id in ids and edge.target_id in ids for edge in capped.edges)
    whole = local_graph(knowledge(), limit=50)
    assert not whole.truncated


def test_dot_escapes_labels() -> None:
    dot = to_dot(local_graph(knowledge(), limit=50))
    assert dot.startswith("digraph")
    assert '"synthetic-claim.demand" -> "synthetic-claim.revenue" [label="CONTRADICTS"]' in dot
    assert "<script>" not in dot


# --- real runs: scope ---------------------------------------------------------------------------


def test_a_run_never_shows_another_runs_records(
    workbench: services.Workbench, fake_run: Callable[[str], str]
) -> None:
    first, second = fake_run("one"), fake_run("two")
    loaded = load_run(workbench.repo, workbench.runs_dir, first)
    assert loaded is not None
    graph = local_graph(loaded, limit=50)
    shown = {node.node_id for node in graph.nodes}
    shown |= {item for row in relation_table(loaded) for item in (row.source_id, row.target_id)}
    assert not any(item.startswith(second) for item in shown)
    assert any(item.startswith(first) for item in shown)
    allowed = set(loaded.manifest.document_ids) | set(loaded.manifest.permitted_span_ids)
    allowed |= set(loaded.manifest.instrument_ids) | set(loaded.subjects)
    assert all(item.startswith(first) or item in allowed for item in shown)
    # The completion fixture's critic records a contradiction (A02).
    assert "CONTRADICTS" in {row.label for row in relation_table(loaded) if row.relation_id}
    drill = assertion_drilldown(loaded, loaded.thesis.assertions[0].assertion_id)  # type: ignore[union-attr]
    assert drill.claims[0].passages[0].span.exact_quote.startswith("Fourth quarter revenue")


def test_an_unfinished_run_has_nothing_to_inspect_yet(workbench: services.Workbench) -> None:
    request, plan = services.plan_case(
        workbench, "supported", RuntimeMode.FAKE, now=NOW, nonce="queued"
    )
    services.submit(workbench, request, plan)
    assert load_run(workbench.repo, workbench.runs_dir, request.run_id) is None
