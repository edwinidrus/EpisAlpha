"""Evidence drilldown, relation table and local graph for one run (plan M5-T02, A8, A21).

Everything here is scoped to one run: its frozen snapshot (documents, permitted spans, claims
and relations) plus the records the run itself created. :func:`load_run` reads them once,
through the hash-verified replay; the other functions are pure over that :class:`RunKnowledge`.

- Recorded relations keep their predicate. Edges read from record fields (a claim's spans and
  subjects, a hypothesis's claims) use the frozen predicates too, with endpoints the vocabulary
  allows. Two lowercase labels are references, never relations: ``cites`` (thesis assertion to
  record) and ``derivation input`` (input claim to derived claim).
- Source and model text come back as plain strings. Rendering them inertly is the caller's job.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from functools import cached_property
from pathlib import Path

from episalpha.contracts.errors import EpisAlphaError, ErrorCode
from episalpha.contracts.knowledge import (
    Claim,
    EvidenceDocument,
    EvidenceSpan,
    Hypothesis,
    RecordKind,
    Relation,
    RelationPredicate,
)
from episalpha.contracts.research import (
    TERMINAL_STATES,
    ResearchMode,
    RunState,
    RuntimeMode,
    SnapshotManifest,
    Thesis,
    ThesisAssertion,
)
from episalpha.research.artifacts import replay
from episalpha.research.derivations import DerivationError, matches, recompute
from episalpha.storage.repository import Repository

CITES = "cites"
DERIVATION_INPUT = "derivation input"


@dataclass(frozen=True)
class RunKnowledge:
    """One run's records and the slice of its snapshot they can reach. Nothing else."""

    run_id: str
    manifest: SnapshotManifest
    thesis: Thesis | None
    persisted: bool
    """False when validation rejected the run's records: saved as artifacts, never persisted."""
    state: RunState
    research_mode: ResearchMode
    runtime: RuntimeMode
    executed_at: datetime
    ended_at: datetime | None
    claims: Mapping[str, Claim]
    hypotheses: Mapping[str, Hypothesis]
    relations: tuple[Relation, ...]
    spans: Mapping[str, EvidenceSpan]
    documents: Mapping[str, EvidenceDocument]
    reviews: Mapping[str, str]
    """The judgment in force per claim or hypothesis; absent means unreviewed."""
    subjects: Mapping[str, RecordKind]
    """The snapshot's instruments and their issuers."""

    @cached_property
    def kinds(self) -> dict[str, RecordKind]:
        """Every node in scope. A node outside this map is never displayed."""
        kinds = dict(self.subjects)
        kinds |= dict.fromkeys(self.documents, RecordKind.EVIDENCE_DOCUMENT)
        kinds |= dict.fromkeys(self.spans, RecordKind.EVIDENCE_SPAN)
        kinds |= dict.fromkeys(self.claims, RecordKind.CLAIM)
        kinds |= dict.fromkeys(self.hypotheses, RecordKind.HYPOTHESIS)
        if self.thesis is not None:
            kinds[self.thesis.thesis_id] = RecordKind.THESIS
        return kinds

    def review(self, record_id: str) -> str:
        return self.reviews.get(record_id, "unreviewed")


def load_run(repo: Repository, runs_root: Path, run_id: str) -> RunKnowledge | None:
    """The run's knowledge, or ``None`` while it is unfinished or never froze a snapshot.

    Raises the replay's ``INTEGRITY_ERROR`` when a saved artifact no longer matches its hash.
    """
    record = repo.get_run(run_id)
    if record is None or record.state not in TERMINAL_STATES or record.snapshot_id is None:
        return None
    saved = replay(repo, runs_root, run_id)
    manifest = SnapshotManifest.model_validate(saved.manifest)
    run_claims = [Claim.model_validate(item) for item in saved.records["claims"]]
    snapshot_claims = [c for i in manifest.permitted_claim_ids if (c := repo.get_claim(i))]
    claims = {c.claim_id: c for c in (*snapshot_claims, *run_claims)}
    hypotheses = [Hypothesis.model_validate(item) for item in saved.records["hypotheses"]]
    spans = {i: s for i in manifest.permitted_span_ids if (s := repo.get_span(i))}
    documents = {i: d for i in manifest.document_ids if (d := repo.get_document(i))}
    subjects: dict[str, RecordKind] = {}
    for instrument_id in manifest.instrument_ids:
        subjects[instrument_id] = RecordKind.INSTRUMENT
        if (instrument := repo.get_instrument(instrument_id)) is not None:
            subjects[instrument.issuer_entity_id] = RecordKind.ENTITY
    permitted = set(manifest.permitted_relation_ids)
    relations = {r.relation_id: r for r in map(Relation.model_validate, saved.records["relations"])}
    for node_id in (*subjects, *documents, *spans, *(c.claim_id for c in snapshot_claims)):
        relations |= {
            r.relation_id: r for r in repo.relations_from(node_id) if r.relation_id in permitted
        }
    reviews = {
        record_id: assessment.judgment.value
        for record_id in (*claims, *(h.hypothesis_id for h in hypotheses))
        if (assessment := repo.current_assessment(record_id)) is not None
    }
    return RunKnowledge(
        run_id=run_id,
        manifest=manifest,
        thesis=Thesis.model_validate(saved.thesis) if saved.thesis else None,
        persisted=bool(saved.records.get("persisted", True)),
        state=record.state,
        research_mode=record.request.research_mode,
        runtime=record.request.runtime_mode,
        executed_at=record.started_at,
        ended_at=record.ended_at,
        claims=claims,
        hypotheses={h.hypothesis_id: h for h in hypotheses},
        relations=tuple(relations[key] for key in sorted(relations)),
        spans=spans,
        documents=documents,
        reviews=reviews,
        subjects=subjects,
    )


# --- drilldown ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class Passage:
    span: EvidenceSpan
    document: EvidenceDocument | None
    cited_by: str
    """The claim citing the span: the drilled claim itself or one of its derivation inputs."""


@dataclass(frozen=True)
class ChainInput:
    claim_id: str
    value: Decimal | None
    unit: str | None
    period_start: datetime | None
    period_end: datetime | None


@dataclass(frozen=True)
class Chain:
    """A derived claim's computation, recomputed here by the registry (A8)."""

    inputs: tuple[ChainInput, ...]
    method: str
    method_version: str
    value: Decimal | None
    """The registry's result; ``None`` when it cannot be recomputed (see ``error``)."""
    unit: str | None
    claimed: Decimal | None
    matches: bool | None
    error: str | None


@dataclass(frozen=True)
class ClaimTrace:
    claim: Claim
    review_status: str
    in_run: bool
    passages: tuple[Passage, ...]
    chain: Chain | None
    contradicts: tuple[str, ...]
    contradicted_by: tuple[str, ...]


@dataclass(frozen=True)
class HypothesisTrace:
    hypothesis: Hypothesis
    review_status: str


@dataclass(frozen=True)
class Drilldown:
    run_id: str
    assertion: ThesisAssertion
    claims: tuple[ClaimTrace, ...]
    hypotheses: tuple[HypothesisTrace, ...]
    missing: tuple[str, ...]
    """Referenced IDs absent from the run's records: shown, never silently dropped."""
    research_cutoff: datetime
    executed_at: datetime
    shared_lineage: tuple[tuple[str, tuple[str, ...]], ...]
    """Source families cited through more than one document (A21): one lineage, not several
    independent confirmations."""


def assertion_drilldown(knowledge: RunKnowledge, assertion_id: str) -> Drilldown:
    """Assertion -> claims -> spans -> passages, with clocks, review status and chains."""
    thesis = knowledge.thesis
    assertion = next(
        (a for a in (thesis.assertions if thesis else ()) if a.assertion_id == assertion_id), None
    )
    if assertion is None:
        raise EpisAlphaError(
            ErrorCode.INVALID_REQUEST,
            f"assertion {assertion_id!r} is not in run {knowledge.run_id}",
        )
    contradictions = [
        r for r in knowledge.relations if r.predicate is RelationPredicate.CONTRADICTS
    ]
    claims = []
    for claim_id in assertion.claim_ids:
        if (claim := knowledge.claims.get(claim_id)) is None:
            continue
        claims.append(
            ClaimTrace(
                claim=claim,
                review_status=knowledge.review(claim_id),
                in_run=claim.run_id == knowledge.run_id,
                passages=claim_passages(knowledge, claim_id),
                chain=derivation_chain(knowledge, claim),
                contradicts=tuple(r.target_id for r in contradictions if r.source_id == claim_id),
                contradicted_by=tuple(
                    r.source_id for r in contradictions if r.target_id == claim_id
                ),
            )
        )
    hypotheses = tuple(
        HypothesisTrace(knowledge.hypotheses[i], knowledge.review(i))
        for i in assertion.hypothesis_ids
        if i in knowledge.hypotheses
    )
    families: dict[str, set[str]] = {}
    for trace in claims:
        for passage in trace.passages:
            if passage.document is not None:
                family = families.setdefault(passage.document.source_family_id, set())
                family.add(passage.document.document_id)
    return Drilldown(
        run_id=knowledge.run_id,
        assertion=assertion,
        claims=tuple(claims),
        hypotheses=hypotheses,
        missing=tuple(
            i
            for i in (*assertion.claim_ids, *assertion.hypothesis_ids)
            if i not in knowledge.claims and i not in knowledge.hypotheses
        ),
        research_cutoff=knowledge.manifest.research_cutoff,
        executed_at=knowledge.executed_at,
        shared_lineage=tuple(
            (name, tuple(sorted(docs))) for name, docs in sorted(families.items()) if len(docs) > 1
        ),
    )


def claim_passages(knowledge: RunKnowledge, claim_id: str) -> tuple[Passage, ...]:
    """The claim's cited passages, then those of its derivation inputs, recursively."""
    return tuple(_passages(knowledge, claim_id, set()))


def _passages(knowledge: RunKnowledge, claim_id: str, seen: set[str]) -> list[Passage]:
    claim = knowledge.claims.get(claim_id)
    if claim is None or claim_id in seen:
        return []
    seen.add(claim_id)
    found = [
        Passage(span, knowledge.documents.get(span.document_id), claim_id)
        for span_id in claim.span_ids
        if (span := knowledge.spans.get(span_id)) is not None
    ]
    for input_id in claim.derivation.input_claim_ids if claim.derivation else ():
        found.extend(_passages(knowledge, input_id, seen))
    return found


def derivation_chain(knowledge: RunKnowledge, claim: Claim) -> Chain | None:
    """The claim's derivation recomputed from its in-scope inputs; ``None`` if not derived."""
    derivation = claim.derivation
    if derivation is None:
        return None
    facts = [
        c.numeric_fact if (c := knowledge.claims.get(i)) else None
        for i in derivation.input_claim_ids
    ]
    inputs = tuple(
        ChainInput(
            claim_id,
            fact.value if fact else None,
            fact.unit if fact else None,
            fact.period_start if fact else None,
            fact.period_end if fact else None,
        )
        for claim_id, fact in zip(derivation.input_claim_ids, facts, strict=True)
    )
    claimed = claim.numeric_fact.value if claim.numeric_fact else None
    value: Decimal | None = None
    unit: str | None = None
    error: str | None = None
    present = [fact for fact in facts if fact is not None]
    if len(present) != len(facts):
        error = "an input claim has no numeric fact in this run's records"
    else:
        try:
            value, unit = recompute(derivation, present)
        except DerivationError as failure:
            error = str(failure)
    return Chain(
        inputs=inputs,
        method=derivation.method,
        method_version=derivation.method_version,
        value=value,
        unit=unit,
        claimed=claimed,
        matches=matches(claimed, value) if claimed is not None and value is not None else None,
        error=error,
    )


# --- relation table and graph ------------------------------------------------------------------


@dataclass(frozen=True)
class RelationRow:
    source_id: str
    source_kind: str
    label: str
    target_id: str
    target_kind: str
    origin: str
    """``recorded`` for a stored relation; else the record whose fields imply the edge."""
    relation_id: str | None = None
    epistemic_status: str | None = None


def relation_table(knowledge: RunKnowledge) -> list[RelationRow]:
    """Every edge between in-scope nodes: recorded relations first, then record fields."""
    kinds = knowledge.kinds
    rows: dict[tuple[str, str, str], RelationRow] = {}

    def add(
        source: str, label: str, target: str, origin: str, relation: Relation | None = None
    ) -> None:
        key = (source, label, target)
        if key in rows or source not in kinds or target not in kinds:
            return
        rows[key] = RelationRow(
            source_id=source,
            source_kind=kinds[source].value,
            label=label,
            target_id=target,
            target_kind=kinds[target].value,
            origin=origin,
            relation_id=relation.relation_id if relation else None,
            epistemic_status=relation.epistemic_status.value if relation else None,
        )

    for relation in knowledge.relations:
        add(relation.source_id, relation.predicate.value, relation.target_id, "recorded", relation)
    for claim_id, claim in sorted(knowledge.claims.items()):
        for span_id in claim.span_ids:
            if (span := knowledge.spans.get(span_id)) is not None:
                add(span.document_id, RelationPredicate.HAS_SPAN.value, span_id, "claim")
                add(span_id, RelationPredicate.REPORTS.value, claim_id, "claim")
        for subject_id in claim.subject_ids:
            add(claim_id, RelationPredicate.ABOUT.value, subject_id, "claim")
        for input_id in claim.derivation.input_claim_ids if claim.derivation else ():
            add(input_id, DERIVATION_INPUT, claim_id, "derivation")
    for hypothesis_id, hypothesis in sorted(knowledge.hypotheses.items()):
        for claim_id in hypothesis.supporting_claim_ids:
            add(claim_id, RelationPredicate.SUPPORTS.value, hypothesis_id, "hypothesis")
        for claim_id in hypothesis.opposing_claim_ids:
            add(claim_id, RelationPredicate.CONTRADICTS.value, hypothesis_id, "hypothesis")
    if knowledge.thesis is not None:
        for assertion in knowledge.thesis.assertions:
            for record_id in (*assertion.claim_ids, *assertion.hypothesis_ids):
                add(knowledge.thesis.thesis_id, CITES, record_id, "thesis")
    return list(rows.values())


@dataclass(frozen=True)
class Node:
    node_id: str
    kind: str
    review_status: str | None
    """Claims and hypotheses only."""


@dataclass(frozen=True)
class Edge:
    source_id: str
    target_id: str
    label: str


@dataclass(frozen=True)
class Graph:
    nodes: tuple[Node, ...]
    edges: tuple[Edge, ...]
    truncated: bool


def local_graph(knowledge: RunKnowledge, center_id: str | None = None, *, limit: int) -> Graph:
    """Breadth-first from ``center_id`` (default: the thesis), cut at ``limit`` nodes."""
    rows = relation_table(knowledge)
    neighbours: dict[str, set[str]] = {}
    for row in rows:
        neighbours.setdefault(row.source_id, set()).add(row.target_id)
        neighbours.setdefault(row.target_id, set()).add(row.source_id)
    if center_id is not None:
        seeds = [center_id]
    elif knowledge.thesis is not None:
        seeds = [knowledge.thesis.thesis_id]
    else:
        seeds = sorted(i for i, c in knowledge.claims.items() if c.run_id == knowledge.run_id)
        seeds += sorted(knowledge.hypotheses)
    kinds = knowledge.kinds
    order = [seed for seed in dict.fromkeys(seeds) if seed in kinds]
    seen = set(order)
    queue = deque(order)
    while queue:
        for neighbour in sorted(neighbours.get(queue.popleft(), ())):
            if neighbour not in seen:
                seen.add(neighbour)
                order.append(neighbour)
                queue.append(neighbour)
    kept = set(order[:limit])
    reviewed = {RecordKind.CLAIM, RecordKind.HYPOTHESIS}
    return Graph(
        nodes=tuple(
            Node(i, kinds[i].value, knowledge.review(i) if kinds[i] in reviewed else None)
            for i in order[:limit]
        ),
        edges=tuple(
            Edge(r.source_id, r.target_id, r.label)
            for r in rows
            if r.source_id in kept and r.target_id in kept
        ),
        truncated=len(order) > limit,
    )


def _dot(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def to_dot(graph: Graph) -> str:
    """Graphviz DOT text. Labels hold IDs, kinds and vocabulary terms only, all escaped."""
    lines = ["digraph run {", "  rankdir=LR;", "  node [shape=box, fontsize=10];"]
    for node in graph.nodes:
        parts = [node.kind, node.node_id, *([node.review_status] if node.review_status else [])]
        color = ', color="red"' if node.review_status == "unsupported" else ""
        label = "\\n".join(_dot(part) for part in parts)
        lines.append(f'  "{_dot(node.node_id)}" [label="{label}"{color}];')
    for edge in graph.edges:
        lines.append(
            f'  "{_dot(edge.source_id)}" -> "{_dot(edge.target_id)}" [label="{_dot(edge.label)}"];'
        )
    lines.append("}")
    return "\n".join(lines)
