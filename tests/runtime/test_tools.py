"""M3-T01 — runtime port, fake runtime, and snapshot-bound typed tools."""

from __future__ import annotations

import inspect
import json
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fixtures.synthetic_knowledge import (
    CONTRADICTING_CLAIM,
    DEMAND_SPAN,
    DOCUMENT_TEXT,
    REPORTED_CLAIM,
    REVENUE_SPAN,
    SYNTHETIC_DOCUMENT,
    SYNTHETIC_HYPOTHESIS,
)
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from episalpha.connectors.prices import AdjustmentBasis, PricePoint, PriceSeries
from episalpha.contracts.errors import ErrorCode
from episalpha.contracts.knowledge import (
    Claim,
    EpistemicStatus,
    Instrument,
    NumericFact,
    Relation,
    RelationPredicate,
    TickerAlias,
)
from episalpha.contracts.research import ResearchMode, RunState, RuntimeContext
from episalpha.evidence.snapshots import build_snapshot, build_view
from episalpha.observability import configure_tracing, shutdown_tracing
from episalpha.research.derivations import recompute
from episalpha.runtime.fake import FakeRuntime, Scenario
from episalpha.runtime.port import ExitReason, ResearchRuntimePort
from episalpha.runtime.tools import TOOL_NAMES, ToolHost
from episalpha.settings import Limits, Settings
from episalpha.storage.objects import ObjectStore

CUTOFF = datetime(2026, 9, 21, tzinfo=UTC)
NOW = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
INSTRUMENT = Instrument(
    instrument_id="synthetic-issuer.eq",
    issuer_entity_id="synthetic-issuer",
    exchange="TESTEX",
    currency="EUR",
    ticker_aliases=(
        TickerAlias(
            ticker="OLDSYN",
            valid_from=datetime(2020, 1, 1, tzinfo=UTC),
            valid_to=datetime(2024, 1, 1, tzinfo=UTC),
        ),
        TickerAlias(ticker="SYN", valid_from=datetime(2024, 1, 1, tzinfo=UTC)),
    ),
)
Q3_REVENUE = REPORTED_CLAIM.model_copy(
    update={
        "claim_id": "synthetic-claim.revenue-q3",
        "numeric_fact": REPORTED_CLAIM.numeric_fact.model_copy(  # type: ignore[union-attr]
            update={
                "value": Decimal("400000000.00"),
                "period_start": datetime(2025, 7, 1, tzinfo=UTC),
                "period_end": datetime(2025, 9, 30, tzinfo=UTC),
            }
        ),
    }
)
CONTRADICTS = Relation(
    relation_id="synthetic-relation.contradicts",
    predicate=RelationPredicate.CONTRADICTS,
    source_id="synthetic-claim.demand",
    target_id="synthetic-claim.revenue",
    evidence_span_ids=("synthetic-span.demand",),
    epistemic_status=EpistemicStatus.REPORTED,
    created_at=datetime(2026, 9, 20, 9, 30, tzinfo=UTC),
)
OUTSIDE_CLAIM = Claim(
    claim_id="outside-claim.future",
    statement="Created after the cutoff, so outside the snapshot.",
    subject_ids=("synthetic-issuer.eq",),
    attribution="nobody",
    epistemic_status=EpistemicStatus.REPORTED,
    span_ids=("synthetic-span.revenue",),
    created_at=datetime(2026, 10, 1, tzinfo=UTC),
)
PRICES = PriceSeries(
    instrument_id="synthetic-issuer.eq",
    source_id="alpha_vantage",
    currency="EUR",
    adjustment_basis=AdjustmentBasis.UNADJUSTED,
    points=(
        PricePoint(trade_date=date(2026, 9, 18), close=Decimal("10.00")),
        PricePoint(trade_date=date(2026, 9, 19), close=Decimal("10.50")),
        PricePoint(trade_date=date(2026, 9, 22), close=Decimal("99.00")),  # after the cutoff
    ),
    fetched_at=NOW,
)


def make_host(limits: Limits | None = None, tool_calls: int = 12, **overrides: Any) -> ToolHost:
    claims = [REPORTED_CLAIM, CONTRADICTING_CLAIM, Q3_REVENUE, OUTSIDE_CLAIM]
    manifest = build_snapshot(
        snapshot_id="snapshot.0001",
        instrument_ids=["synthetic-issuer.eq"],
        research_cutoff=CUTOFF,
        research_mode=ResearchMode.HISTORICAL_RECONSTRUCTION,
        documents=[SYNTHETIC_DOCUMENT],
        spans=[REVENUE_SPAN, DEMAND_SPAN],
        claims=claims,
        relations=[CONTRADICTS],
        source_version="test-1",
        frozen_at=NOW,
    )
    view = build_view(
        manifest,
        [SYNTHETIC_DOCUMENT],
        [REVENUE_SPAN, DEMAND_SPAN],
        {"synthetic-doc.v1": DOCUMENT_TEXT},
    )
    context = RuntimeContext(
        run_id="run.0001",
        snapshot=manifest,
        stage=RunState.RESEARCHING,
        validated_hypothesis_ids=overrides.pop("validated_hypothesis_ids", ()),
        remaining_model_requests=8,
        remaining_tool_calls=tool_calls,
        remaining_wall_time_seconds=300,
    )
    arguments: dict[str, Any] = {
        "claims": claims,
        "relations": [CONTRADICTS],
        "instruments": [INSTRUMENT],
        "market": PRICES,
    }
    arguments.update(overrides)
    return ToolHost(view, context, limits or Limits(), **arguments)


@pytest.fixture
def host() -> ToolHost:
    return make_host()


# --- happy paths ---------------------------------------------------------------------------


def test_resolve_instrument_uses_the_alias_valid_at_the_cutoff(host: ToolHost) -> None:
    assert host.resolve_instrument("SYN").payload == {"instrument_id": "synthetic-issuer.eq"}
    stale = host.resolve_instrument("OLDSYN")
    assert stale.error_code is ErrorCode.NO_DATA
    assert host.resolve_instrument("NOPE").error_code is ErrorCode.NO_DATA


def test_search_evidence_returns_exact_quotes_from_the_snapshot(host: ToolHost) -> None:
    result = host.search_evidence("demand", limit=3)
    assert result.ok
    (hit,) = result.payload["hits"]
    assert hit == {
        "span_id": "synthetic-span.demand",
        "document_id": "synthetic-doc.v1",
        "quote": DEMAND_SPAN.exact_quote,
        "locator": "paragraph-2",
    }


def test_get_evidence_span(host: ToolHost) -> None:
    result = host.get_evidence_span("synthetic-span.revenue")
    assert result.payload["quote"] == REVENUE_SPAN.exact_quote
    assert result.payload["document_id"] == "synthetic-doc.v1"


def test_market_context_is_truncated_at_the_cutoff_and_labels_adjustment(host: ToolHost) -> None:
    result = host.get_market_context("synthetic-issuer.eq")
    assert result.ok
    assert result.payload["adjustment_basis"] == "unadjusted"
    assert [p["date"] for p in result.payload["points"]] == ["2026-09-18", "2026-09-19"]
    assert result.payload["latest_close"] == "10.50"
    assert result.payload["multi_day_return"] is None
    assert "unadjusted" in result.payload["multi_day_return_reason"]


def test_market_context_without_series_is_no_data() -> None:
    assert make_host(market=None).get_market_context("synthetic-issuer.eq").error_code is (
        ErrorCode.NO_DATA
    )


def test_support_and_contradictions_are_scoped(host: ToolHost) -> None:
    result = host.get_support_and_contradictions("synthetic-claim.revenue")
    assert result.payload == {
        "record_id": "synthetic-claim.revenue",
        "supports": [],
        "contradicts": [
            {"relation_id": "synthetic-relation.contradicts", "other_id": "synthetic-claim.demand"}
        ],
    }


def test_validated_current_run_hypothesis_is_visible() -> None:
    host = make_host(hypotheses=[SYNTHETIC_HYPOTHESIS])
    assert (
        host.get_support_and_contradictions(SYNTHETIC_HYPOTHESIS.hypothesis_id).error_code
        is ErrorCode.NOT_AUTHORIZED
    )  # not yet validated by the host

    validated = make_host(
        hypotheses=[SYNTHETIC_HYPOTHESIS], validated_hypothesis_ids=("synthetic-hypothesis.demand",)
    )
    result = validated.get_support_and_contradictions("synthetic-hypothesis.demand")
    assert result.payload["supports"] == [
        {"relation_id": None, "other_id": "synthetic-claim.demand"}
    ]
    assert result.payload["contradicts"] == [
        {"relation_id": None, "other_id": "synthetic-claim.revenue"}
    ]


def test_get_numeric_facts(host: ToolHost) -> None:
    result = host.get_numeric_facts("synthetic-issuer.eq", ["revenue"])
    facts = result.payload["facts"]
    assert [fact["claim_id"] for fact in facts] == [
        "synthetic-claim.revenue",
        "synthetic-claim.revenue-q3",
    ]
    assert facts[0]["value"] == "412000000.00"
    assert facts[0]["unit"] == "EUR"


def test_compute_derivation_equals_recompute(host: ToolHost) -> None:
    result = host.compute_derivation(
        "pct_change", "1", ["synthetic-claim.revenue-q3", "synthetic-claim.revenue"]
    )
    assert result.ok
    numeric = [Q3_REVENUE.numeric_fact, REPORTED_CLAIM.numeric_fact]
    from episalpha.contracts.knowledge import Derivation

    expected, unit = recompute(
        Derivation(
            method="pct_change",
            method_version="1",
            input_claim_ids=("synthetic-claim.revenue-q3", "synthetic-claim.revenue"),
        ),
        [item for item in numeric if isinstance(item, NumericFact)],
    )
    assert result.payload["value"] == str(expected) == "0.03"
    assert result.payload["unit"] == unit == "ratio"


def test_compute_derivation_unknown_method_is_a_typed_error(host: ToolHost) -> None:
    result = host.compute_derivation("cagr", "1", ["synthetic-claim.revenue"])
    assert not result.ok
    assert result.error_code is ErrorCode.INVALID_OUTPUT
    assert "unknown method" in result.payload["error"]


# --- scope ---------------------------------------------------------------------------------


def test_outside_snapshot_ids_are_not_authorized(host: ToolHost) -> None:
    assert host.get_evidence_span("synthetic-span.ghost").error_code is ErrorCode.NOT_AUTHORIZED
    assert host.get_support_and_contradictions("outside-claim.future").error_code is (
        ErrorCode.NOT_AUTHORIZED
    )
    assert (
        host.compute_derivation(
            "difference", "1", ["outside-claim.future", "synthetic-claim.revenue"]
        ).error_code
        is ErrorCode.NOT_AUTHORIZED
    )
    assert host.get_market_context("other.eq").error_code is ErrorCode.NOT_AUTHORIZED


def test_no_tool_accepts_a_cutoff_path_url_or_sql() -> None:
    forbidden = {"cutoff", "research_cutoff", "as_of", "date", "path", "url", "sql", "query_sql"}
    for name in TOOL_NAMES:
        parameters = set(inspect.signature(getattr(ToolHost, name)).parameters) - {"self"}
        assert not parameters & forbidden, name


# --- limits --------------------------------------------------------------------------------


def test_search_hit_cap_holds() -> None:
    host = make_host(limits=Limits(max_evidence_search_hits=1))
    result = host.search_evidence("quarter demand", limit=50)
    assert len(result.payload["hits"]) == 1
    assert result.payload["limit_applied"] == 1


def test_oversize_result_is_budget_exceeded_never_truncated() -> None:
    host = make_host(limits=Limits(max_tool_result_bytes=256, max_request_body_bytes=1024))
    result = host.search_evidence("quarter demand", limit=5)
    assert not result.ok
    assert result.error_code is ErrorCode.BUDGET_EXCEEDED
    assert "hits" not in result.payload


def test_tool_call_budget_runs_out() -> None:
    host = make_host(tool_calls=2)
    assert host.get_evidence_span("synthetic-span.revenue").ok
    assert host.get_evidence_span("synthetic-span.revenue").ok
    third = host.get_evidence_span("synthetic-span.revenue")
    assert third.error_code is ErrorCode.BUDGET_EXCEEDED
    assert host.tool_calls_used == 2


def test_result_hash_is_stable(host: ToolHost) -> None:
    first = host.get_evidence_span("synthetic-span.revenue")
    second = host.get_evidence_span("synthetic-span.revenue")
    assert first.result_hash == second.result_hash
    assert len(first.result_hash) == 64
    assert first.bytes == len(
        json.dumps(
            {"ok": True, "payload": first.payload, "error_code": None},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    )


# --- propose_skill (A13) -------------------------------------------------------------------


def proposal(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "title": "Check guidance against the prior range",
        "when_to_use": "When a filing restates full-year guidance.",
        "procedure_steps": ["Find the prior range.", "Compute the revision host-side."],
        "rationale": "Revisions are easy to misstate without the prior range.",
        "evidence_span_ids": ["synthetic-span.demand"],
    }
    base.update(overrides)
    return base


def test_propose_skill_is_data_only_and_capped(host: ToolHost) -> None:
    first = host.propose_skill(**proposal())
    second = host.propose_skill(**proposal(title="Second"))
    third = host.propose_skill(**proposal(title="Third"))

    assert first.ok and second.ok
    assert first.payload["proposal_id"] != second.payload["proposal_id"]
    assert third.error_code is ErrorCode.BUDGET_EXCEEDED
    assert [p.title for p in host.proposals] == [
        "Check guidance against the prior range",
        "Second",
    ]


def test_propose_skill_rejects_unknown_spans_and_oversize(host: ToolHost) -> None:
    unknown = host.propose_skill(**proposal(evidence_span_ids=["synthetic-span.ghost"]))
    assert unknown.error_code is ErrorCode.NOT_AUTHORIZED
    oversize = host.propose_skill(**proposal(procedure_steps=["x" * 5000]))
    assert oversize.error_code is ErrorCode.INVALID_REQUEST
    assert host.proposals == ()


# --- observability -------------------------------------------------------------------------


@pytest.fixture
def spans(tmp_path: Path) -> Iterator[InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    settings = Settings.model_validate(
        {"paths": {"project_root": tmp_path, "data_root": tmp_path / "data"}}
    )
    configure_tracing(settings, extra_exporter=exporter)
    yield exporter
    shutdown_tracing()


def test_each_tool_call_is_one_span_with_hashes(
    spans: InMemorySpanExporter, tmp_path: Path
) -> None:
    host = make_host()
    host.search_evidence("demand", limit=2)
    host.get_evidence_span("synthetic-span.ghost")

    search, refused = spans.get_finished_spans()
    assert search.name == "tool.search_evidence"
    assert search.attributes is not None
    assert search.attributes["openinference.span.kind"] == "RETRIEVER"
    assert search.attributes["retrieval.documents.0.document.id"] == "synthetic-span.demand"
    assert refused.name == "tool.get_evidence_span"
    assert refused.attributes is not None
    assert refused.attributes["openinference.span.kind"] == "TOOL"
    assert refused.attributes["episalpha.error_code"] == "NOT_AUTHORIZED"
    assert len(str(refused.attributes["episalpha.result_hash"])) == 64

    shutdown_tracing()
    jsonl = (tmp_path / "data" / "logs" / "spans.jsonl").read_text()
    assert DEMAND_SPAN.exact_quote not in jsonl  # payload text never reaches the JSONL
    assert "tool.parameters_hash" in jsonl


# --- fake runtime --------------------------------------------------------------------------


def fake_context(stage: RunState = RunState.RESEARCHING) -> RuntimeContext:
    return make_host().context.model_copy(update={"stage": stage})


def test_fake_runtime_satisfies_the_port_and_labels_fixtures(tmp_path: Path) -> None:
    store = ObjectStore(tmp_path / "objects")
    runtime: ResearchRuntimePort = FakeRuntime(store, Scenario.COMPLETION, now=lambda: NOW)
    result = runtime.run_stage(RunState.RESEARCHING, fake_context())

    assert result.completed
    assert result.exit_reason == ExitReason.COMPLETED
    assert result.candidate_payload_hash is not None
    payload = json.loads(store.get(result.candidate_payload_hash))
    assert payload["fixture"] is True
    assert payload["source"].endswith("tests/fixtures/runtime/completion.json#RESEARCHING")


@pytest.mark.parametrize(
    ("scenario", "stage", "completed", "reason"),
    [
        (Scenario.PROVIDER_FAILURE, RunState.RESEARCHING, False, ExitReason.PROVIDER_FAILURE),
        (Scenario.TIMEOUT, RunState.RESEARCHING, False, ExitReason.TIMEOUT),
        (Scenario.PARTIAL, RunState.CRITIQUING, False, ExitReason.PARTIAL),
        (Scenario.ABSTENTION, RunState.SYNTHESIZING, True, ExitReason.COMPLETED),
        (Scenario.INVALID_REFERENCES, RunState.RESEARCHING, True, ExitReason.COMPLETED),
    ],
)
def test_fake_scenarios(
    tmp_path: Path, scenario: Scenario, stage: RunState, completed: bool, reason: ExitReason
) -> None:
    store = ObjectStore(tmp_path / "objects")
    result = FakeRuntime(store, scenario, now=lambda: NOW).run_stage(stage, fake_context(stage))
    assert result.completed is completed
    assert result.exit_reason == reason


def test_partial_output_is_preserved(tmp_path: Path) -> None:
    store = ObjectStore(tmp_path / "objects")
    result = FakeRuntime(store, Scenario.PARTIAL, now=lambda: NOW).run_stage(
        RunState.CRITIQUING, fake_context(RunState.CRITIQUING)
    )
    assert result.candidate_payload_hash is not None
    assert json.loads(store.get(result.candidate_payload_hash))["fixture"] is True


def test_fake_cancellation(tmp_path: Path) -> None:
    runtime = FakeRuntime(ObjectStore(tmp_path / "o"), Scenario.COMPLETION, now=lambda: NOW)
    runtime.cancel()
    result = runtime.run_stage(RunState.RESEARCHING, fake_context())
    assert not result.completed
    assert result.exit_reason == ExitReason.CANCELLED


def test_search_matches_words_not_whole_phrases(host: ToolHost) -> None:
    result = host.search_evidence("weaker demand outlook for the first half", limit=3)
    assert [hit["span_id"] for hit in result.payload["hits"]] == ["synthetic-span.demand"]
    ranked = host.search_evidence("revenue demand quarter", limit=3)
    assert [hit["span_id"] for hit in ranked.payload["hits"]] == [
        "synthetic-span.revenue",
        "synthetic-span.demand",
    ]
    assert host.search_evidence("the and of", limit=3).error_code is ErrorCode.INVALID_REQUEST
