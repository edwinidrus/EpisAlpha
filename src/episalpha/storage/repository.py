"""Typed persistence for the canonical records (plan M2-T01).

Every write registers the record's node kind first, so relation endpoints are enforced by
SQLite's own foreign keys rather than by hope. Every read reconstructs the validated contract
from its stored payload, so a row that no longer satisfies the schema fails loudly at load time
instead of flowing onward as a plain dict.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Sequence
from typing import Any

from episalpha.contracts.errors import EpisAlphaError, ErrorCode
from episalpha.contracts.knowledge import (
    Claim,
    Contract,
    Entity,
    Event,
    EvidenceDocument,
    EvidenceSpan,
    Hypothesis,
    Instrument,
    RecordKind,
    Relation,
    SemanticAssessment,
)
from episalpha.contracts.research import (
    RunRecord,
    RunState,
    SnapshotManifest,
    StageResult,
    Thesis,
)


class IntegrityError(EpisAlphaError):
    """A stored row contradicts something already recorded."""

    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.INTEGRITY_ERROR, message)


def _dump(record: Contract) -> str:
    """Serialize a contract deterministically, so an identical record stores identical bytes."""
    return json.dumps(record.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


def _load[C: Contract](model: type[C], row: sqlite3.Row) -> C:
    return model.model_validate(json.loads(row["payload"]))


class Repository:
    """Reads and writes canonical records.

    The caller owns transaction boundaries via :func:`episalpha.storage.db.transaction`; nothing
    here commits on its own, so a multi-record write is all-or-nothing.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    # --- node registry ------------------------------------------------------------------

    def _register_node(self, node_id: str, kind: RecordKind) -> None:
        existing = self.connection.execute(
            "SELECT kind FROM node WHERE node_id = ?", (node_id,)
        ).fetchone()
        if existing is None:
            self.connection.execute(
                "INSERT INTO node (node_id, kind) VALUES (?, ?)", (node_id, kind.value)
            )
            return
        if existing["kind"] != kind.value:
            raise IntegrityError(
                f"{node_id!r} is already registered as {existing['kind']!r}; it cannot also be "
                f"a {kind.value!r}"
            )

    def node_kind(self, node_id: str) -> RecordKind | None:
        row = self.connection.execute(
            "SELECT kind FROM node WHERE node_id = ?", (node_id,)
        ).fetchone()
        return RecordKind(row["kind"]) if row else None

    # --- knowledge records ---------------------------------------------------------------

    def save_entity(self, entity: Entity) -> None:
        self._register_node(entity.entity_id, RecordKind.ENTITY)
        self.connection.execute(
            "INSERT OR REPLACE INTO entity (entity_id, canonical_name, payload) VALUES (?, ?, ?)",
            (entity.entity_id, entity.canonical_name, _dump(entity)),
        )

    def save_instrument(self, instrument: Instrument) -> None:
        self._register_node(instrument.instrument_id, RecordKind.INSTRUMENT)
        self.connection.execute(
            "INSERT OR REPLACE INTO instrument "
            "(instrument_id, issuer_entity_id, currency, payload) VALUES (?, ?, ?, ?)",
            (
                instrument.instrument_id,
                instrument.issuer_entity_id,
                instrument.currency,
                _dump(instrument),
            ),
        )

    def save_document(self, document: EvidenceDocument) -> None:
        """Store one document *version*. An existing version is never rewritten in place."""
        existing = self.get_document(document.document_id)
        if existing is not None and existing != document:
            raise IntegrityError(
                f"document {document.document_id!r} already exists with different content; "
                "store a revision under a new id instead of overwriting a version"
            )
        self._register_node(document.document_id, RecordKind.EVIDENCE_DOCUMENT)
        self.connection.execute(
            "INSERT OR REPLACE INTO evidence_document (document_id, source_family_id, "
            "source_uri, payload_hash, parsed_text_hash, parser_version, availability_basis, "
            "public_available_at, ingested_at, revises_document_id, payload) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                document.document_id,
                document.source_family_id,
                document.source_uri,
                document.payload_hash,
                document.parsed_text_hash,
                document.parser_version,
                document.availability_basis.value,
                document.public_available_at.isoformat() if document.public_available_at else None,
                document.ingested_at.isoformat(),
                document.revises_document_id,
                _dump(document),
            ),
        )

    def save_span(self, span: EvidenceSpan) -> None:
        self._register_node(span.span_id, RecordKind.EVIDENCE_SPAN)
        self.connection.execute(
            "INSERT OR REPLACE INTO evidence_span (span_id, document_id, start_offset, "
            "end_offset, exact_quote, payload) VALUES (?, ?, ?, ?, ?, ?)",
            (
                span.span_id,
                span.document_id,
                span.start_offset,
                span.end_offset,
                span.exact_quote,
                _dump(span),
            ),
        )

    def save_claim(self, claim: Claim) -> None:
        self._register_node(claim.claim_id, RecordKind.CLAIM)
        self.connection.execute(
            "INSERT OR REPLACE INTO claim (claim_id, statement, epistemic_status, "
            "semantic_review_status, created_at, run_id, payload) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                claim.claim_id,
                claim.statement,
                claim.epistemic_status.value,
                claim.semantic_review_status.value,
                claim.created_at.isoformat(),
                claim.run_id,
                _dump(claim),
            ),
        )

    def save_event(self, event: Event) -> None:
        self._register_node(event.event_id, RecordKind.EVENT)
        self.connection.execute(
            "INSERT OR REPLACE INTO event (event_id, event_type, occurred_at, payload) "
            "VALUES (?, ?, ?, ?)",
            (event.event_id, event.event_type, event.occurred_at.isoformat(), _dump(event)),
        )

    def save_hypothesis(self, hypothesis: Hypothesis) -> None:
        self._register_node(hypothesis.hypothesis_id, RecordKind.HYPOTHESIS)
        self.connection.execute(
            "INSERT OR REPLACE INTO hypothesis (hypothesis_id, created_at, payload) "
            "VALUES (?, ?, ?)",
            (hypothesis.hypothesis_id, hypothesis.created_at.isoformat(), _dump(hypothesis)),
        )

    def save_relation(self, relation: Relation) -> None:
        """Endpoints must already be registered; SQLite refuses the insert otherwise."""
        self.connection.execute(
            "INSERT OR REPLACE INTO relation (relation_id, predicate, source_id, target_id, "
            "epistemic_status, created_at, run_id, payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                relation.relation_id,
                relation.predicate.value,
                relation.source_id,
                relation.target_id,
                relation.epistemic_status.value,
                relation.created_at.isoformat(),
                relation.run_id,
                _dump(relation),
            ),
        )

    def save_assessment(self, assessment: SemanticAssessment) -> None:
        """Append a judgment. Superseding writes a new row; the old one stays readable."""
        self.connection.execute(
            "INSERT INTO semantic_assessment (assessment_id, subject_id, judgment, "
            "reviewer_type, reviewer_identity, assessed_at, supersedes_assessment_id, payload) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                assessment.assessment_id,
                assessment.subject_id,
                assessment.judgment.value,
                assessment.reviewer_type.value,
                assessment.reviewer_identity,
                assessment.assessed_at.isoformat(),
                assessment.supersedes_assessment_id,
                _dump(assessment),
            ),
        )

    def save_thesis(self, thesis: Thesis) -> None:
        self._register_node(thesis.thesis_id, RecordKind.THESIS)
        self.connection.execute(
            "INSERT OR REPLACE INTO thesis (thesis_id, run_id, instrument_id, snapshot_id, "
            "stance, created_at, payload) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                thesis.thesis_id,
                thesis.run_id,
                thesis.instrument_id,
                thesis.snapshot_id,
                thesis.stance.value,
                thesis.created_at.isoformat(),
                _dump(thesis),
            ),
        )

    # --- reads -------------------------------------------------------------------------

    def _get[C: Contract](self, table: str, column: str, key: str, model: type[C]) -> C | None:
        row = self.connection.execute(
            f"SELECT payload FROM {table} WHERE {column} = ?",
            (key,),  # noqa: S608 - fixed names
        ).fetchone()
        return _load(model, row) if row else None

    def get_entity(self, entity_id: str) -> Entity | None:
        return self._get("entity", "entity_id", entity_id, Entity)

    def get_instrument(self, instrument_id: str) -> Instrument | None:
        return self._get("instrument", "instrument_id", instrument_id, Instrument)

    def get_document(self, document_id: str) -> EvidenceDocument | None:
        return self._get("evidence_document", "document_id", document_id, EvidenceDocument)

    def get_span(self, span_id: str) -> EvidenceSpan | None:
        return self._get("evidence_span", "span_id", span_id, EvidenceSpan)

    def get_claim(self, claim_id: str) -> Claim | None:
        return self._get("claim", "claim_id", claim_id, Claim)

    def get_hypothesis(self, hypothesis_id: str) -> Hypothesis | None:
        return self._get("hypothesis", "hypothesis_id", hypothesis_id, Hypothesis)

    def get_thesis(self, thesis_id: str) -> Thesis | None:
        return self._get("thesis", "thesis_id", thesis_id, Thesis)

    def documents_in_family(self, source_family_id: str) -> tuple[EvidenceDocument, ...]:
        """Every retained version of one source family, oldest ingestion first."""
        rows = self.connection.execute(
            "SELECT payload FROM evidence_document WHERE source_family_id = ? "
            "ORDER BY ingested_at, document_id",
            (source_family_id,),
        ).fetchall()
        return tuple(_load(EvidenceDocument, row) for row in rows)

    def spans_for_document(self, document_id: str) -> tuple[EvidenceSpan, ...]:
        rows = self.connection.execute(
            "SELECT payload FROM evidence_span WHERE document_id = ? ORDER BY start_offset",
            (document_id,),
        ).fetchall()
        return tuple(_load(EvidenceSpan, row) for row in rows)

    def relations_from(self, source_id: str) -> tuple[Relation, ...]:
        rows = self.connection.execute(
            "SELECT payload FROM relation WHERE source_id = ? ORDER BY relation_id", (source_id,)
        ).fetchall()
        return tuple(_load(Relation, row) for row in rows)

    def assessments_for(self, subject_id: str) -> tuple[SemanticAssessment, ...]:
        """Full judgment history for one subject, oldest first."""
        rows = self.connection.execute(
            "SELECT payload FROM semantic_assessment WHERE subject_id = ? "
            "ORDER BY assessed_at, assessment_id",
            (subject_id,),
        ).fetchall()
        return tuple(_load(SemanticAssessment, row) for row in rows)

    def current_assessment(self, subject_id: str) -> SemanticAssessment | None:
        """The judgment in force: the one no other assessment supersedes."""
        history = self.assessments_for(subject_id)
        superseded = {a.supersedes_assessment_id for a in history if a.supersedes_assessment_id}
        current = [a for a in history if a.assessment_id not in superseded]
        return current[-1] if current else None

    def search_spans(self, query: str, limit: int) -> tuple[EvidenceSpan, ...]:
        """Full-text search over quoted passages, ranked by FTS5's own relevance."""
        rows = self.connection.execute(
            "SELECT s.payload FROM evidence_span_fts f "
            "JOIN evidence_span s ON s.rowid = f.rowid "
            "WHERE evidence_span_fts MATCH ? ORDER BY rank LIMIT ?",
            (query, limit),
        ).fetchall()
        return tuple(_load(EvidenceSpan, row) for row in rows)

    # --- snapshots and runs ---------------------------------------------------------------

    def save_snapshot(self, manifest: SnapshotManifest) -> None:
        existing = self.get_snapshot(manifest.snapshot_id)
        if existing is not None and existing != manifest:
            raise IntegrityError(
                f"snapshot {manifest.snapshot_id!r} already exists with different content; a "
                "frozen snapshot is immutable"
            )
        self.connection.execute(
            "INSERT OR REPLACE INTO snapshot (snapshot_id, snapshot_hash, research_cutoff, "
            "frozen_at, payload) VALUES (?, ?, ?, ?, ?)",
            (
                manifest.snapshot_id,
                manifest.snapshot_hash,
                manifest.research_cutoff.isoformat(),
                manifest.frozen_at.isoformat(),
                _dump(manifest),
            ),
        )

    def get_snapshot(self, snapshot_id: str) -> SnapshotManifest | None:
        return self._get("snapshot", "snapshot_id", snapshot_id, SnapshotManifest)

    def admit_run(self, record: RunRecord) -> RunRecord:
        """Admit a run idempotently.

        If the idempotency key has been used, the existing run is returned unchanged and no
        second run is created — re-submitting a request must not spend the model budget twice.
        """
        existing = self.run_by_idempotency_key(record.request.idempotency_key)
        if existing is not None:
            return existing
        self._write_run(record)
        return record

    def _write_run(self, record: RunRecord) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO run (run_id, idempotency_key, instrument_id, state, "
            "snapshot_id, thesis_id, error_code, reason, started_at, ended_at, payload) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                record.request.run_id,
                record.request.idempotency_key,
                record.request.instrument_id,
                record.state.value,
                record.snapshot_id,
                record.thesis_id,
                record.error_code.value if record.error_code else None,
                record.reason,
                record.started_at.isoformat(),
                record.ended_at.isoformat() if record.ended_at else None,
                _dump(record),
            ),
        )

    def update_run(self, record: RunRecord) -> None:
        """Persist a run that already exists. Refuses to invent one."""
        if self.get_run(record.request.run_id) is None:
            raise IntegrityError(f"run {record.request.run_id!r} has not been admitted")
        self._write_run(record)

    def get_run(self, run_id: str) -> RunRecord | None:
        return self._get("run", "run_id", run_id, RunRecord)

    def run_by_idempotency_key(self, key: str) -> RunRecord | None:
        return self._get("run", "idempotency_key", key, RunRecord)

    def runs_in_state(self, state: RunState) -> tuple[RunRecord, ...]:
        rows = self.connection.execute(
            "SELECT payload FROM run WHERE state = ? ORDER BY started_at", (state.value,)
        ).fetchall()
        return tuple(_load(RunRecord, row) for row in rows)

    def save_stage_result(self, run_id: str, attempt: int, stage: StageResult) -> None:
        """Record a stage checkpoint. An incomplete stage is kept, not discarded."""
        self.connection.execute(
            "INSERT OR REPLACE INTO stage_result (run_id, attempt, stage, completed, "
            "exit_reason, model_requests, tool_calls, prompt_tokens, completion_tokens, "
            "started_at, ended_at, payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                attempt,
                stage.stage.value,
                int(stage.completed),
                stage.exit_reason,
                stage.usage.model_requests,
                stage.usage.tool_calls,
                stage.usage.prompt_tokens,
                stage.usage.completion_tokens,
                stage.started_at.isoformat(),
                stage.ended_at.isoformat(),
                _dump(stage),
            ),
        )

    def stage_results(self, run_id: str) -> tuple[StageResult, ...]:
        rows = self.connection.execute(
            "SELECT payload FROM stage_result WHERE run_id = ? ORDER BY started_at, attempt",
            (run_id,),
        ).fetchall()
        return tuple(_load(StageResult, row) for row in rows)

    def run_usage(self, run_id: str) -> dict[str, Any]:
        """Summed reported usage across attempts. Unknown token counts stay unknown."""
        row = self.connection.execute(
            "SELECT COALESCE(SUM(model_requests), 0) AS model_requests, "
            "COALESCE(SUM(tool_calls), 0) AS tool_calls, "
            "SUM(prompt_tokens) AS prompt_tokens, SUM(completion_tokens) AS completion_tokens "
            "FROM stage_result WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        return {
            "model_requests": row["model_requests"],
            "tool_calls": row["tool_calls"],
            "prompt_tokens": row["prompt_tokens"],
            "completion_tokens": row["completion_tokens"],
            "cost_eur": None,
        }

    # --- bulk helpers --------------------------------------------------------------------

    def save_all(self, records: Iterable[Contract]) -> None:
        """Save a mixed batch, registering nodes before the edges that reference them."""
        ordered: Sequence[Contract] = sorted(records, key=lambda r: isinstance(r, Relation))
        for record in ordered:
            match record:
                case Entity():
                    self.save_entity(record)
                case Instrument():
                    self.save_instrument(record)
                case EvidenceDocument():
                    self.save_document(record)
                case EvidenceSpan():
                    self.save_span(record)
                case Claim():
                    self.save_claim(record)
                case Event():
                    self.save_event(record)
                case Hypothesis():
                    self.save_hypothesis(record)
                case Thesis():
                    self.save_thesis(record)
                case Relation():
                    self.save_relation(record)
                case SemanticAssessment():
                    self.save_assessment(record)
                case _:
                    raise TypeError(f"no persistence rule for {type(record).__name__}")
