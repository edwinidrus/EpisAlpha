"""Frozen snapshot assembly and scoped access (plan M2-T04).

A snapshot is the entire world a research run can see. Two properties make that worth anything:

* **It is frozen.** Its hash is computed from its contents, so later ingestion cannot alter it
  and any drift is detectable rather than invisible.
* **It is closed.** :class:`SnapshotView` refuses ids outside the manifest, so an agent cannot
  widen its own access by asking for something it was not given.

Completeness is recorded, not implied. A snapshot missing the price source because the source
refused says so, which is what keeps "we could not look" apart from "there was nothing there".
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime

from episalpha.contracts.errors import EpisAlphaError, ErrorCode
from episalpha.contracts.knowledge import (
    Claim,
    EvidenceDocument,
    EvidenceSpan,
    Relation,
)
from episalpha.contracts.research import (
    ResearchMode,
    SnapshotManifest,
    SourceCompleteness,
)
from episalpha.evidence.temporal import select_current_versions

ONTOLOGY_VERSION = 1


class NotInSnapshotError(EpisAlphaError):
    """Something outside the frozen snapshot was requested."""

    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.NOT_AUTHORIZED, message)


def compute_snapshot_hash(
    *,
    instrument_ids: Sequence[str],
    research_cutoff: datetime,
    document_ids: Sequence[str],
    span_ids: Sequence[str],
    claim_ids: Sequence[str],
    relation_ids: Sequence[str],
    source_version: str,
    ontology_version: int,
) -> str:
    """Hash the snapshot's contents, deterministically.

    Sorted ids and a canonical separator mean the same inputs always produce the same hash,
    whatever order they were assembled in. ``frozen_at`` is excluded on purpose: rebuilding the
    same evidence set at a different moment should be recognisable as the same set.
    """
    material = json.dumps(
        {
            "instrument_ids": sorted(instrument_ids),
            "research_cutoff": research_cutoff.isoformat(),
            "document_ids": sorted(document_ids),
            "span_ids": sorted(span_ids),
            "claim_ids": sorted(claim_ids),
            "relation_ids": sorted(relation_ids),
            "source_version": source_version,
            "ontology_version": ontology_version,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def build_snapshot(
    *,
    snapshot_id: str,
    instrument_ids: Sequence[str],
    research_cutoff: datetime,
    research_mode: ResearchMode,
    documents: Iterable[EvidenceDocument],
    spans: Iterable[EvidenceSpan],
    claims: Iterable[Claim] = (),
    relations: Iterable[Relation] = (),
    source_completeness: Sequence[SourceCompleteness] = (),
    source_version: str,
    frozen_at: datetime,
) -> SnapshotManifest:
    """Freeze the eligible evidence for one research cutoff.

    Only the latest *qualifying* version of each source family is included: not today's latest,
    and not invariably the first-reported one. Spans, claims and relations are then filtered to
    those whose documents actually made it in, so the snapshot cannot reference something a
    reader could not open.
    """
    eligible_documents = select_current_versions(documents, research_cutoff, research_mode)
    document_ids = {document.document_id for document in eligible_documents}

    eligible_spans = tuple(span for span in spans if span.document_id in document_ids)
    span_ids = {span.span_id for span in eligible_spans}

    eligible_claims = tuple(
        claim
        for claim in claims
        if claim.created_at <= research_cutoff and set(claim.span_ids) <= span_ids
    )
    claim_ids = {claim.claim_id for claim in eligible_claims}

    permitted = document_ids | span_ids | claim_ids | set(instrument_ids)
    eligible_relations = tuple(
        relation
        for relation in relations
        if relation.source_id in permitted and relation.target_id in permitted
    )

    return SnapshotManifest(
        snapshot_id=snapshot_id,
        snapshot_hash=compute_snapshot_hash(
            instrument_ids=list(instrument_ids),
            research_cutoff=research_cutoff,
            document_ids=sorted(document_ids),
            span_ids=sorted(span_ids),
            claim_ids=sorted(claim_ids),
            relation_ids=sorted(r.relation_id for r in eligible_relations),
            source_version=source_version,
            ontology_version=ONTOLOGY_VERSION,
        ),
        instrument_ids=tuple(instrument_ids),
        research_cutoff=research_cutoff,
        document_ids=tuple(sorted(document_ids)),
        permitted_span_ids=tuple(sorted(span_ids)),
        permitted_claim_ids=tuple(sorted(claim_ids)),
        permitted_relation_ids=tuple(sorted(r.relation_id for r in eligible_relations)),
        source_completeness=tuple(source_completeness),
        source_version=source_version,
        ontology_version=ONTOLOGY_VERSION,
        frozen_at=frozen_at,
    )


def verify_snapshot(manifest: SnapshotManifest) -> bool:
    """Does the manifest still hash to its recorded hash?"""
    return manifest.snapshot_hash == compute_snapshot_hash(
        instrument_ids=list(manifest.instrument_ids),
        research_cutoff=manifest.research_cutoff,
        document_ids=list(manifest.document_ids),
        span_ids=list(manifest.permitted_span_ids),
        claim_ids=list(manifest.permitted_claim_ids),
        relation_ids=list(manifest.permitted_relation_ids),
        source_version=manifest.source_version,
        ontology_version=manifest.ontology_version,
    )


@dataclass(frozen=True)
class SnapshotView:
    """Read-only access to exactly what a snapshot contains, and nothing else.

    The cutoff comes from the manifest, never from a caller-supplied argument, so an agent
    cannot widen its own window by passing a later date.
    """

    manifest: SnapshotManifest
    documents: dict[str, EvidenceDocument]
    spans: dict[str, EvidenceSpan]
    document_texts: dict[str, str]

    @property
    def research_cutoff(self) -> datetime:
        return self.manifest.research_cutoff

    def document(self, document_id: str) -> EvidenceDocument:
        if document_id not in self.manifest.document_ids:
            raise NotInSnapshotError(
                f"document {document_id!r} is not in snapshot {self.manifest.snapshot_id!r}"
            )
        return self.documents[document_id]

    def span(self, span_id: str) -> EvidenceSpan:
        if span_id not in self.manifest.permitted_span_ids:
            raise NotInSnapshotError(
                f"span {span_id!r} is not in snapshot {self.manifest.snapshot_id!r}"
            )
        return self.spans[span_id]

    def text(self, document_id: str) -> str:
        self.document(document_id)
        return self.document_texts[document_id]

    def search(self, query: str, limit: int) -> tuple[EvidenceSpan, ...]:
        """Substring search confined to the snapshot's own spans.

        Deliberately simple and deliberately scoped: the database's FTS index covers everything
        ever ingested, which is a larger world than this run is allowed to see.
        """
        needle = query.casefold()
        hits = [
            self.spans[span_id]
            for span_id in self.manifest.permitted_span_ids
            if needle in self.spans[span_id].exact_quote.casefold()
        ]
        hits.sort(key=lambda span: (span.document_id, span.start_offset))
        return tuple(hits[:limit])

    @property
    def missing_sources(self) -> tuple[str, ...]:
        """Sources that were attempted and did not deliver. Visible, never silently absent."""
        return tuple(
            entry.source_id
            for entry in self.manifest.source_completeness
            if entry.attempted and not entry.succeeded
        )

    @property
    def has_essential_evidence(self) -> bool:
        """A snapshot with no documents cannot support research; it abstains instead."""
        return bool(self.manifest.document_ids)


def build_view(
    manifest: SnapshotManifest,
    documents: Iterable[EvidenceDocument],
    spans: Iterable[EvidenceSpan],
    document_texts: dict[str, str],
) -> SnapshotView:
    """Assemble a view, keeping only records the manifest actually permits."""
    permitted_documents = {
        document.document_id: document
        for document in documents
        if document.document_id in manifest.document_ids
    }
    permitted_spans = {
        span.span_id: span for span in spans if span.span_id in manifest.permitted_span_ids
    }
    missing = set(manifest.permitted_span_ids) - set(permitted_spans)
    if missing:
        raise NotInSnapshotError(
            f"snapshot {manifest.snapshot_id!r} permits spans that were not supplied: "
            f"{sorted(missing)}"
        )
    return SnapshotView(
        manifest=manifest,
        documents=permitted_documents,
        spans=permitted_spans,
        document_texts={
            key: value for key, value in document_texts.items() if key in permitted_documents
        },
    )
