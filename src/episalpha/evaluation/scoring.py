"""Deterministic per-case metrics and pooling (plan section 12.3, M6-T01).

Every metric is a :class:`Ratio`: a case-level numerator and denominator, pooled by summing over
the same cases. A ratio with no denominator is ``N/A``, never 0 or 1, and one metric never stands
in for another (M6 article 6). The rules that keep omission from winning:

- the label decides the denominators of recall, abstention and completion, so a failed or empty
  run stays in them and scores zero there;
- precision-type metrics (citation, supported-claim, numeric) count what was emitted; emitting
  nothing makes them ``N/A`` for that case, never perfect, and completion catches the omission.

Only persisted records count as the run's answer: a ``REJECTED`` run's records were never
persisted, so it answered nothing. Numeric correctness (A8) reads the model's own proposals from
each stage's first attempt, before any repair.

This module only reads. Scores carry IDs and counts, never label text (M6 article 12).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from episalpha.contracts.knowledge import (
    Claim,
    Derivation,
    EpistemicStatus,
    EvidenceDocument,
    NumericFact,
    Relation,
    RelationPredicate,
)
from episalpha.contracts.research import ResearchMode, RunState, SnapshotManifest
from episalpha.evaluation.cases import ExpectedContradiction, ExpectedFact, Labels
from episalpha.evidence.temporal import is_eligible
from episalpha.research.artifacts import RunArtifacts
from episalpha.research.derivations import DerivationError, matches, recompute
from episalpha.storage.repository import Repository

METRICS = (
    "citation_correctness",
    "numeric_correctness",
    "supported_claim_precision",
    "required_fact_recall",
    "contradiction_recall",
    "correct_abstention",
    "completion",
)
FACTUAL = (EpistemicStatus.REPORTED, EpistemicStatus.DERIVED)


@dataclass(frozen=True)
class Ratio:
    numerator: int = 0
    denominator: int = 0

    @property
    def value(self) -> Decimal | None:
        """``None`` is ``N/A``: there was nothing this metric applies to."""
        return Decimal(self.numerator) / Decimal(self.denominator) if self.denominator else None

    def __add__(self, other: Ratio) -> Ratio:
        return Ratio(self.numerator + other.numerator, self.denominator + other.denominator)

    def __str__(self) -> str:
        return f"{self.numerator}/{self.denominator}" if self.denominator else "N/A"


@dataclass(frozen=True)
class RunOutcome:
    """What one finished run produced, read from its hash-verified artifacts."""

    run_id: str
    state: RunState
    claims: tuple[Claim, ...] = ()
    """Persisted run claims only."""
    relations: tuple[Relation, ...] = ()
    hypotheses: int = 0
    proposals: tuple[dict[str, Any], ...] = ()
    """``{"stage", "attempt", "payload"}`` per stage attempt, payloads as the model sent them."""
    permitted_span_ids: tuple[str, ...] = ()
    documents: tuple[EvidenceDocument, ...] = ()
    """The snapshot's documents, to recheck eligibility at the cutoff."""
    research_cutoff: datetime | None = None
    research_mode: ResearchMode = ResearchMode.HISTORICAL_RECONSTRUCTION
    failed_checks: tuple[str, ...] = ()
    model_requests: int = 0
    latency_seconds: int | None = None


def load_outcome(repo: Repository, runs_root: Path, run_id: str) -> RunOutcome:
    """Read a finished run. Every artifact read is verified against the run's index."""
    record = repo.get_run(run_id)
    if record is None:
        raise ValueError(f"run {run_id!r} does not exist")
    artifacts = RunArtifacts(runs_root, run_id)
    saved = artifacts.hashes
    records = artifacts.read("records") if "records" in saved else {}
    # A REJECTED run's records were never persisted: it answered nothing.
    persisted: dict[str, Any] = records if records.get("persisted") else {}
    manifest = (
        SnapshotManifest.model_validate(artifacts.read("manifest")) if "manifest" in saved else None
    )
    validation = artifacts.read("validation") if "validation" in saved else None
    proposals = []
    for name in sorted(saved):
        if name.startswith("stages/"):
            stage, _, attempt = name.removeprefix("stages/").rpartition("-")
            payload = artifacts.read(name)["payload"]
            proposals.append({"stage": stage, "attempt": int(attempt), "payload": payload})
    documents = (
        tuple(d for i in manifest.document_ids if (d := repo.get_document(i)) is not None)
        if manifest
        else ()
    )
    ended = record.ended_at
    return RunOutcome(
        run_id=run_id,
        state=record.state,
        claims=tuple(Claim.model_validate(c) for c in persisted.get("claims", [])),
        relations=tuple(Relation.model_validate(r) for r in persisted.get("relations", [])),
        hypotheses=len(persisted.get("hypotheses", [])),
        proposals=tuple(proposals),
        permitted_span_ids=manifest.permitted_span_ids if manifest else (),
        documents=documents,
        research_cutoff=record.request.research_cutoff,
        research_mode=record.request.research_mode,
        failed_checks=tuple(
            check["check"] for check in (validation or {}).get("checks", []) if not check["passed"]
        ),
        model_requests=record.usage.model_requests,
        latency_seconds=int((ended - record.started_at).total_seconds()) if ended else None,
    )


@dataclass(frozen=True)
class CaseScore:
    case_id: str
    run_id: str
    state: RunState
    metrics: dict[str, Ratio]
    recovered_facts: tuple[str, ...] = ()
    recovered_contradictions: tuple[str, ...] = ()
    unsupported_claims: tuple[str, ...] = ()
    """Factual claims a recorded assessment judged ``unsupported``."""
    hypotheses: int = 0
    temporal_violations: int = 0
    boundary_violations: int = 0
    reference_violations: int = 0
    model_requests: int = 0
    latency_seconds: int | None = None


def score_case(
    outcome: RunOutcome, labels: Labels, assessments: Mapping[str, str] | None = None
) -> CaseScore:
    """Score one run against its labels. ``assessments`` maps claim ID to recorded judgment."""
    judged = assessments or {}
    factual = [claim for claim in outcome.claims if claim.epistemic_status in FACTUAL]
    citable = labels.citable_span_ids
    links = [span for claim in factual for span in claim.span_ids]
    facts = tuple(item.fact_id for item in labels.facts if _recovered(item, factual))
    spans_of = {claim.claim_id: set(claim.span_ids) for claim in outcome.claims}
    contradictions = tuple(
        item.contradiction_id
        for item in labels.contradictions
        if _contradiction_found(item, outcome.relations, spans_of)
    )
    decision = labels.should_abstain
    required = (
        {RunState.ABSTAINED}
        if decision
        else {RunState.RESEARCH_COMPLETED}
        if decision is False
        else {RunState.RESEARCH_COMPLETED, RunState.ABSTAINED}
    )
    done = int(outcome.state in required)
    metrics = {
        "citation_correctness": Ratio(sum(span in citable for span in links), len(links)),
        "numeric_correctness": _numeric(outcome),
        "supported_claim_precision": Ratio(
            sum(judged.get(c.claim_id) == "supported" for c in factual), len(factual)
        ),
        "required_fact_recall": Ratio(len(facts), len(labels.facts)),
        "contradiction_recall": Ratio(len(contradictions), len(labels.contradictions)),
        "correct_abstention": Ratio(done, 1) if decision is not None else Ratio(),
        "completion": Ratio(done, 1),
    }
    permitted = set(outcome.permitted_span_ids)
    cutoff = outcome.research_cutoff
    return CaseScore(
        case_id=labels.case_id,
        run_id=outcome.run_id,
        state=outcome.state,
        metrics=metrics,
        recovered_facts=facts,
        recovered_contradictions=contradictions,
        unsupported_claims=tuple(
            c.claim_id for c in factual if judged.get(c.claim_id) == "unsupported"
        ),
        hypotheses=outcome.hypotheses,
        temporal_violations=sum(
            not is_eligible(d, cutoff, outcome.research_mode) for d in outcome.documents
        )
        if cutoff is not None
        else 0,
        boundary_violations=sum(
            span not in permitted for claim in outcome.claims for span in claim.span_ids
        ),
        reference_violations=len(outcome.failed_checks),
        model_requests=outcome.model_requests,
        latency_seconds=outcome.latency_seconds,
    )


def _recovered(fact: ExpectedFact, claims: Sequence[Claim]) -> bool:
    for claim in claims:
        if not set(claim.span_ids) & set(fact.span_ids):
            continue
        number = claim.numeric_fact
        if fact.value is None:
            return True
        if number is not None and number.value == fact.value:
            if fact.unit is None or number.unit == fact.unit:
                return True
    return False


def _contradiction_found(
    expected: ExpectedContradiction, relations: Iterable[Relation], spans_of: Mapping[str, set[str]]
) -> bool:
    side_a, side_b = set(expected.side_a_span_ids), set(expected.side_b_span_ids)
    for relation in relations:
        if relation.predicate is not RelationPredicate.CONTRADICTS:
            continue
        source = spans_of.get(relation.source_id, set())
        target = spans_of.get(relation.target_id, set())
        if (source & side_a and target & side_b) or (source & side_b and target & side_a):
            return True
    return False


def _numeric(outcome: RunOutcome) -> Ratio:
    """Derived numbers the model proposed in each stage's first attempt that recompute (A8)."""
    first: dict[str, int] = {}
    for item in outcome.proposals:
        first[item["stage"]] = min(first.get(item["stage"], item["attempt"]), item["attempt"])
    proposed: list[dict[str, Any]] = []
    for item in outcome.proposals:
        if item["attempt"] == first[item["stage"]] and isinstance(item["payload"], dict):
            for key in ("claims", "counter_claims"):
                proposed.extend(c for c in item["payload"].get(key) or [] if isinstance(c, dict))
    facts: dict[str, NumericFact] = {
        claim.claim_id: claim.numeric_fact for claim in outcome.claims if claim.numeric_fact
    }
    for candidate in proposed:
        fact = _fact(candidate.get("numeric_fact"))
        if fact is not None and candidate.get("key"):
            facts.setdefault(f"{outcome.run_id}.{candidate['key']}", fact)
    derived = [c for c in proposed if c.get("derivation") and c.get("numeric_fact")]
    correct = 0
    for candidate in derived:
        claimed = _fact(candidate["numeric_fact"])
        try:
            derivation = Derivation.model_validate(candidate["derivation"])
            inputs = [facts[claim_id] for claim_id in derivation.input_claim_ids]
            value, unit = recompute(derivation, inputs)
        except (ValidationError, KeyError, DerivationError):
            continue  # unrecomputable: proposed, and not correct
        if claimed is not None and claimed.unit == unit and matches(claimed.value, value):
            correct += 1
    return Ratio(correct, len(derived))


def _fact(raw: Any) -> NumericFact | None:
    try:
        return NumericFact.model_validate(raw)
    except ValidationError:
        return None


@dataclass(frozen=True)
class PooledScore:
    cases: int
    metrics: dict[str, Ratio]
    temporal_violations: int = 0
    boundary_violations: int = 0
    reference_violations: int = 0
    unsupported_claims: int = 0
    model_requests: tuple[int, ...] = ()
    latencies: tuple[int | None, ...] = ()
    case_ids: tuple[str, ...] = ()


def pool(scores: Sequence[CaseScore]) -> PooledScore:
    """Sum numerators and denominators over the same cases. Nothing is dropped."""
    metrics = {name: sum((s.metrics[name] for s in scores), Ratio()) for name in METRICS}
    return PooledScore(
        cases=len(scores),
        metrics=metrics,
        temporal_violations=sum(s.temporal_violations for s in scores),
        boundary_violations=sum(s.boundary_violations for s in scores),
        reference_violations=sum(s.reference_violations for s in scores),
        unsupported_claims=sum(len(s.unsupported_claims) for s in scores),
        model_requests=tuple(s.model_requests for s in scores),
        latencies=tuple(s.latency_seconds for s in scores),
        case_ids=tuple(s.case_id for s in scores),
    )


def as_json(score: CaseScore | PooledScore) -> dict[str, Any]:
    """A JSON-ready dict; each metric as numerator, denominator and display value."""
    data = asdict(score)
    data["metrics"] = {
        name: {"numerator": r.numerator, "denominator": r.denominator, "display": str(r)}
        for name, r in score.metrics.items()
    }
    if isinstance(score, CaseScore):
        data["state"] = score.state.value
    return data
