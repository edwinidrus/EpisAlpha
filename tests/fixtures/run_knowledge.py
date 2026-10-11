"""SYNTHETIC run knowledge for the M5 view and export tests. Not real research.

One hand-built :class:`RunKnowledge`: a reported claim, a contradicting claim, a reported prior
figure quoted from a *copy* of the release (same source family, A21) whose passage carries an
HTML payload, a derived growth claim (A8), a hypothesis, one recorded contradiction, a thesis.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from fixtures.synthetic_knowledge import (
    CONTRADICTING_CLAIM,
    CREATED_AT,
    DEMAND_SPAN,
    REPORTED_CLAIM,
    REVENUE_SPAN,
    SYNTHETIC_DOCUMENT,
    SYNTHETIC_HYPOTHESIS,
)

from episalpha.contracts.knowledge import (
    Claim,
    Derivation,
    EpistemicStatus,
    EvidenceSpan,
    NumericFact,
    RecordKind,
    Relation,
    RelationPredicate,
)
from episalpha.contracts.research import (
    ResearchMode,
    ResearchStance,
    RunState,
    RuntimeMode,
    SnapshotManifest,
    Thesis,
    ThesisAssertion,
    ThesisSection,
)
from episalpha.knowledge.query import (
    RunKnowledge,
)

NOW = datetime(2026, 10, 11, 9, 0, tzinfo=UTC)
RUN = "run-0123456789ab"
HASH = "c" * 64
SCRIPT = "<script>alert('x')</script><b>bold</b> **not markdown**"

PRIOR_SPAN = EvidenceSpan(
    span_id="synthetic-span.prior",
    document_id="synthetic-doc.copy",
    start_offset=0,
    end_offset=len(SCRIPT),
    exact_quote=SCRIPT,
    section_locator="paragraph-9",
)
# A republished copy of the same release: the same source family, so not an independent source.
COPY_DOCUMENT = SYNTHETIC_DOCUMENT.model_copy(
    update={"document_id": "synthetic-doc.copy", "source_uri": "https://example.invalid/copy"}
)
PRIOR_CLAIM = REPORTED_CLAIM.model_copy(
    update={
        "claim_id": "synthetic-claim.prior",
        "span_ids": ("synthetic-span.prior",),
        "numeric_fact": REPORTED_CLAIM.numeric_fact.model_copy(  # type: ignore[union-attr]
            update={"value": Decimal("400000000.00")}
        ),
    }
)
DERIVED_CLAIM = Claim(
    claim_id=f"{RUN}.d1",
    statement="Revenue grew 3.0% on the prior figure.",
    subject_ids=("synthetic-issuer.eq",),
    attribution="EpisAlpha derivation",
    epistemic_status=EpistemicStatus.DERIVED,
    derivation=Derivation(
        method="pct_change",
        method_version="1",
        input_claim_ids=("synthetic-claim.prior", "synthetic-claim.revenue"),
    ),
    numeric_fact=NumericFact(
        metric="revenue growth",
        value="0.030",
        unit="ratio",
        period_start=datetime(2025, 10, 1, tzinfo=UTC),
        period_end=datetime(2025, 12, 31, tzinfo=UTC),
        accounting_basis="IFRS consolidated, unaudited",
        source_context="derived",
    ),
    created_at=CREATED_AT,
    run_id=RUN,
)
CONTRADICTS = Relation(
    relation_id=f"{RUN}.r1",
    predicate=RelationPredicate.CONTRADICTS,
    source_id="synthetic-claim.demand",
    target_id="synthetic-claim.revenue",
    evidence_span_ids=("synthetic-span.demand",),
    epistemic_status=EpistemicStatus.REPORTED,
    created_at=CREATED_AT,
    run_id=RUN,
)


def thesis(*assertions: ThesisAssertion) -> Thesis:
    return Thesis(
        thesis_id=f"{RUN}.thesis",
        run_id=RUN,
        instrument_id="synthetic-issuer.eq",
        research_cutoff=NOW,
        research_mode=ResearchMode.HISTORICAL_RECONSTRUCTION,
        horizon_trading_days=20,
        stance=ResearchStance.WATCH,
        assertions=assertions,
        next_inquiry="Check the next filing.",
        snapshot_id="snapshot-0001",
        snapshot_hash=HASH,
        harness_id="harness.baseline",
        model_identifier="fixture",
        created_at=NOW,
    )


ASSERTIONS = (
    ThesisAssertion(
        assertion_id=f"{RUN}.a1",
        section=ThesisSection.OBSERVATION,
        text="Revenue was EUR 412.0 million.",
        claim_ids=("synthetic-claim.revenue",),
    ),
    ThesisAssertion(
        assertion_id=f"{RUN}.a2",
        section=ThesisSection.OBSERVATION,
        text="Revenue grew 3.0%.",
        claim_ids=(f"{RUN}.d1",),
    ),
    ThesisAssertion(
        assertion_id=f"{RUN}.a3",
        section=ThesisSection.INTERPRETATION,
        text="Demand may soften.",
        claim_ids=("synthetic-claim.demand",),
        hypothesis_ids=("synthetic-hypothesis.demand",),
    ),
)


def knowledge(*extra_claims: Claim) -> RunKnowledge:
    claims = (REPORTED_CLAIM, CONTRADICTING_CLAIM, PRIOR_CLAIM, DERIVED_CLAIM, *extra_claims)
    return RunKnowledge(
        run_id=RUN,
        manifest=SnapshotManifest(
            snapshot_id="snapshot-0001",
            snapshot_hash=HASH,
            instrument_ids=("synthetic-issuer.eq",),
            research_cutoff=NOW,
            document_ids=("synthetic-doc.v1", "synthetic-doc.copy"),
            permitted_span_ids=(
                "synthetic-span.revenue",
                "synthetic-span.demand",
                PRIOR_SPAN.span_id,
            ),
            source_version="test",
            ontology_version=1,
            frozen_at=NOW,
        ),
        thesis=thesis(*ASSERTIONS),
        persisted=True,
        state=RunState.RESEARCH_COMPLETED,
        research_mode=ResearchMode.HISTORICAL_RECONSTRUCTION,
        runtime=RuntimeMode.FAKE,
        executed_at=NOW,
        ended_at=NOW,
        claims={item.claim_id: item for item in claims},
        hypotheses={SYNTHETIC_HYPOTHESIS.hypothesis_id: SYNTHETIC_HYPOTHESIS},
        relations=(CONTRADICTS,),
        spans={s.span_id: s for s in (REVENUE_SPAN, DEMAND_SPAN, PRIOR_SPAN)},
        documents={d.document_id: d for d in (SYNTHETIC_DOCUMENT, COPY_DOCUMENT)},
        reviews={"synthetic-claim.demand": "unsupported"},
        subjects={
            "synthetic-issuer.eq": RecordKind.INSTRUMENT,
            "synthetic-issuer": RecordKind.ENTITY,
        },
    )
