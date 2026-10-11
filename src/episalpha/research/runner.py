"""The research runner: one run, eight stages, an honest ending (plan M4-T01, section 3.6).

    1. admit idempotently        5. critic, fresh context, validated records only
    2. freeze the snapshot       6. synthesizer builds the Thesis from validated records
    3. researcher                7. deterministic validation, at most one bounded repair
    4. validate, map IDs         8. persist, then declare the terminal state

The runtime (fake or Hermes) only proposes. The runner parses each submission, assigns
canonical IDs (``<run_id>.<key>``), refuses any ID that already exists, validates references
and recomputes derived numbers with the M1 validator, and passes only validated records to
later stages. Every state change goes through ``RunRecord.transition``; every stage result is
persisted before the run moves on; a provider failure is ``FAILED``, never an abstention.

The run is one trace: ``research.run`` with ``snapshot.freeze``, ``stage.<name>``,
``validation``, ``repair.attempt`` and ``run.persist`` beneath it (M4 constitution article 9).
"""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from episalpha.connectors.prices import PriceSeries
from episalpha.contracts.errors import EpisAlphaError, ErrorCode
from episalpha.contracts.knowledge import (
    Claim,
    Derivation,
    Entity,
    EpistemicStatus,
    EvidenceDocument,
    EvidenceSpan,
    Hypothesis,
    Instrument,
    NumericFact,
    Relation,
    RelationPredicate,
)
from episalpha.contracts.research import (
    TERMINAL_STATES,
    RunRecord,
    RunRequest,
    RunState,
    RuntimeContext,
    SourceCompleteness,
    StageResult,
    Thesis,
    ThesisAssertion,
    Usage,
    ValidationReport,
)
from episalpha.evidence.snapshots import SnapshotView, build_snapshot, build_view
from episalpha.observability import SpanKind, annotate, bind_run, event, span, trace_id_hex
from episalpha.research.artifacts import RunArtifacts
from episalpha.research.validation import RecordSet, failed_checks, validate
from episalpha.runtime.candidates import (
    CandidateClaim,
    CritiqueCandidate,
    ResearchCandidate,
    ThesisCandidate,
    parse_candidate,
)
from episalpha.runtime.port import ExitReason, ResearchRuntimePort
from episalpha.runtime.tools import ToolHost
from episalpha.settings import Settings
from episalpha.storage.db import transaction
from episalpha.storage.objects import ObjectStore
from episalpha.storage.repository import Repository

STAGES = (RunState.RESEARCHING, RunState.CRITIQUING, RunState.SYNTHESIZING)
DEFAULT_HORIZON_TRADING_DAYS = 20
"""ponytail: the request carries no horizon yet; the longest hypothesis horizon wins, else 20."""


@dataclass(frozen=True)
class Evidence:
    """Everything a run may freeze. Supersets are fine: the snapshot keeps only what qualifies."""

    documents: tuple[EvidenceDocument, ...] = ()
    spans: tuple[EvidenceSpan, ...] = ()
    document_texts: Mapping[str, str] = field(default_factory=dict)
    claims: tuple[Claim, ...] = ()
    relations: tuple[Relation, ...] = ()
    entities: tuple[Entity, ...] = ()
    instruments: tuple[Instrument, ...] = ()
    market: PriceSeries | None = None
    source_completeness: tuple[SourceCompleteness, ...] = ()
    source_version: str = "episalpha-0.1"
    price_source_id: str | None = None


EvidenceLoader = Callable[[RunRequest], Evidence]


# --- admission, claims, cancellation ---------------------------------------------------------


def _refuse(message: str) -> EpisAlphaError:
    return EpisAlphaError(ErrorCode.INVALID_REQUEST, message)


def admit(repo: Repository, request: RunRequest, *, now: datetime) -> RunRecord:
    """Admit a run. The same idempotency key returns the same run; one active job at a time."""
    with transaction(repo.connection):
        existing = repo.run_by_idempotency_key(request.idempotency_key)
        if existing is not None:
            return existing
        active = [
            row["run_id"]
            for row in repo.connection.execute(
                "SELECT run_id FROM run WHERE state NOT IN ({})".format(
                    ",".join("?" for _ in TERMINAL_STATES)
                ),
                [state.value for state in TERMINAL_STATES],
            )
        ]
        if active:
            raise _refuse(
                f"a research job is already active ({active[0]}); v0.1 runs one at a time"
            )
        record = RunRecord(request=request, state=RunState.QUEUED, started_at=now)
        return repo.admit_run(record)


def claim(repo: Repository, run_id: str, worker_id: str, *, now: datetime) -> RunRecord:
    """Atomically lease a queued run to one worker. A second claim fails."""
    try:
        with transaction(repo.connection):
            record = repo.get_run(run_id)
            if record is None:
                raise _refuse(f"run {run_id!r} has not been admitted")
            if record.state is not RunState.QUEUED:
                raise _refuse(f"run {run_id!r} is {record.state.value}, not QUEUED")
            repo.connection.execute(
                "INSERT INTO run_lease (run_id, worker_id, claimed_at) VALUES (?, ?, ?)",
                (run_id, worker_id, now.isoformat()),
            )
    except sqlite3.IntegrityError:
        raise _refuse(f"run {run_id!r} is already claimed by another worker") from None
    return record


def request_cancel(repo: Repository, run_id: str, *, now: datetime) -> None:
    """Persist a cancellation request; the runner checks it before every stage."""
    with transaction(repo.connection):
        repo.connection.execute(
            "INSERT OR IGNORE INTO run_cancel (run_id, requested_at) VALUES (?, ?)",
            (run_id, now.isoformat()),
        )


def cancel_requested(repo: Repository, run_id: str) -> bool:
    row = repo.connection.execute("SELECT 1 FROM run_cancel WHERE run_id = ?", (run_id,))
    return row.fetchone() is not None


def lease_holder(repo: Repository, run_id: str) -> str | None:
    row = repo.connection.execute("SELECT worker_id FROM run_lease WHERE run_id = ?", (run_id,))
    found = row.fetchone()
    return str(found["worker_id"]) if found else None


def recover(
    repo: Repository,
    runner: ResearchRunner,
    run_id: str,
    runtime: ResearchRuntimePort,
    *,
    worker_id: str,
    now: datetime,
) -> RunRecord:
    """Explicitly resume an interrupted run as a new attempt.

    The stale lease is removed on purpose (never taken over silently), completed stages are
    reused, and the interrupted stage runs again as attempt N+1 with the old attempt kept.
    """
    record = repo.get_run(run_id)
    if record is None:
        raise _refuse(f"run {run_id!r} does not exist")
    if record.state in TERMINAL_STATES:
        raise _refuse(f"run {run_id!r} already ended as {record.state.value}; nothing to recover")
    with transaction(repo.connection):
        repo.connection.execute("DELETE FROM run_lease WHERE run_id = ?", (run_id,))
        repo.connection.execute(
            "INSERT INTO run_lease (run_id, worker_id, claimed_at) VALUES (?, ?, ?)",
            (run_id, worker_id, now.isoformat()),
        )
    return runner.execute(run_id, runtime, resume=record.state is not RunState.QUEUED)


# --- the runner ------------------------------------------------------------------------------


class _Invalid(Exception):
    """A stage's submission failed host validation; the message lists why."""


class _Stop(Exception):
    """End the run in a terminal state."""

    def __init__(
        self,
        state: RunState,
        reason: str,
        code: ErrorCode | None = None,
        via_validation: bool = False,
    ) -> None:
        super().__init__(reason)
        self.state = state
        self.reason = reason
        self.code = code
        self.via_validation = via_validation


_EXIT_TERMINALS: dict[ExitReason, tuple[RunState, ErrorCode | None]] = {
    ExitReason.PROVIDER_FAILURE: (RunState.FAILED, ErrorCode.SOURCE_FAILED),
    ExitReason.BUDGET_EXCEEDED: (RunState.FAILED, ErrorCode.BUDGET_EXCEEDED),
    ExitReason.TIMEOUT: (RunState.TIMED_OUT, ErrorCode.BUDGET_EXCEEDED),
    ExitReason.CANCELLED: (RunState.CANCELLED, None),
}


def _exit_reason(text: str) -> ExitReason:
    try:
        return ExitReason(text.split(":", 1)[0])
    except ValueError:
        return ExitReason.INVALID_OUTPUT


class ResearchRunner:
    """Drives one claimed run on any :class:`ResearchRuntimePort`."""

    def __init__(
        self,
        repo: Repository,
        objects: ObjectStore,
        settings: Settings,
        loader: EvidenceLoader,
        *,
        artifacts_root: Any,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        lineage: Mapping[str, str] | None = None,
    ) -> None:
        self.lineage = dict(lineage or {})
        self.repo = repo
        self.objects = objects
        self.settings = settings
        self.loader = loader
        self.artifacts_root = artifacts_root
        self._now = now
        self._reset()

    def _reset(self) -> None:
        self.record: RunRecord | None = None
        self.evidence = Evidence()
        self.view: SnapshotView | None = None
        self.claims: dict[str, Claim] = {}
        self.hypotheses: dict[str, Hypothesis] = {}
        self.relations: list[Relation] = []
        self.missing: list[str] = []
        self.critique: dict[str, Any] = {}
        self.warnings: list[str] = []
        self.stages: list[StageResult] = []
        self.attempts: dict[RunState, int] = {}
        self.repairs_left = self.settings.limits.max_output_repairs
        self.repair_note = ""
        self.requests = 0
        self.tool_calls = 0
        self.prompt_tokens: int | None = 0
        self.completion_tokens: int | None = 0
        self.thesis: Thesis | None = None
        self.started = time.monotonic()

    # --- hooks the Hermes runtime calls ---------------------------------------------------

    def tools_for(self, stage: RunState, context: RuntimeContext) -> ToolHost:
        assert self.view is not None
        return ToolHost(
            self.view,
            context,
            self.settings.limits,
            claims=(*self.evidence.claims, *self.claims.values()),
            relations=self.evidence.relations,
            instruments=self.evidence.instruments,
            hypotheses=self.hypotheses.values(),
            market=self.evidence.market,
            price_source_id=self.evidence.price_source_id,
        )

    def brief_for(self, stage: RunState, context: RuntimeContext) -> str:
        assert self.record is not None
        request = self.record.request
        lines = [
            f"RUN_ID: {context.run_id}",
            f"Instrument: {request.instrument_id}. Research cutoff: "
            f"{context.research_cutoff.isoformat()}. Mode: {request.research_mode.value}.",
            f"Question: {request.question}",
        ]
        if stage is not RunState.RESEARCHING:
            lines.append("Validated records (cite these IDs exactly):")
            for claim_ in self.claims.values():
                label = "counter-evidence" if claim_.attribution.startswith("critic") else "claim"
                spans_ = ", ".join(claim_.span_ids)
                lines.append(f"- {claim_.claim_id} ({label}; spans {spans_}): {claim_.statement}")
            for hypothesis in self.hypotheses.values():
                lines.append(f"- {hypothesis.hypothesis_id} (hypothesis): {hypothesis.mechanism}")
        if stage is RunState.SYNTHESIZING and self.critique:
            lines.append(f"Critique: {json.dumps(self.critique)}")
        if self.repair_note:
            lines.append(
                "Your previous submission for this stage was rejected by the host. Fix exactly "
                f"these problems and submit again: {self.repair_note}"
            )
        return "\n".join(lines)

    # --- the run ---------------------------------------------------------------------------

    def execute(
        self, run_id: str, runtime: ResearchRuntimePort, *, resume: bool = False
    ) -> RunRecord:
        """Drive a claimed run to a terminal state. ``resume`` continues an interrupted run:
        completed stages are re-accepted from their saved payloads, never re-run."""
        self._reset()
        record = self.repo.get_run(run_id)
        if record is None:
            raise _refuse(f"run {run_id!r} has not been admitted")
        if lease_holder(self.repo, run_id) is None:
            raise _refuse(f"run {run_id!r} has not been claimed by a worker")
        self.record = record
        self._runtime = runtime
        self.artifacts = RunArtifacts(self.artifacts_root, run_id)
        with (
            bind_run(run_id),
            span(
                "research.run",
                SpanKind.CHAIN,
                **{
                    "episalpha.instrument_id": record.request.instrument_id,
                    "episalpha.runtime_mode": record.request.runtime_mode.value,
                    "episalpha.research_mode": record.request.research_mode.value,
                    "input.value": record.request.question,
                    "episalpha.recovered": resume,
                },
            ) as root,
        ):
            self.trace_id = trace_id_hex(root)
            try:
                self._run(runtime, resume)
            except _Stop as stop:
                self._finish(stop, runtime)
            final = self.record
            assert final is not None
            annotate(
                root,
                **{
                    "episalpha.state": final.state.value,
                    "episalpha.reason": final.reason[:200],
                    "episalpha.error_code": final.error_code.value if final.error_code else "",
                    "episalpha.model_requests": final.usage.model_requests,
                    "episalpha.tool_calls": final.usage.tool_calls,
                },
            )
        return final

    def _run(self, runtime: ResearchRuntimePort, resume: bool) -> None:
        assert self.record is not None
        self._check_cancel()
        reusable: dict[RunState, dict[str, Any]] = {}
        if resume and self.record.snapshot_id is not None:
            reusable = self._resume_state()
            self._refreeze(self.record.snapshot_id)
        else:
            self._freeze()
        for stage in STAGES:
            if stage in reusable:
                try:
                    self._accept(stage, reusable[stage])
                    continue
                except _Invalid:
                    pass  # not reusable after all: run it as a new attempt
            self._stage(stage, runtime)
        self._validate_and_finish(runtime)

    def _resume_state(self) -> dict[RunState, dict[str, Any]]:
        """Rebuild counters and history; return the payloads of stages that completed."""
        assert self.record is not None
        history = self.repo.stage_results(self._run_id)
        self.stages = list(history)
        rows = self.repo.connection.execute(
            "SELECT stage, MAX(attempt) AS attempts FROM stage_result WHERE run_id = ? "
            "GROUP BY stage",
            (self._run_id,),
        ).fetchall()
        self.attempts = {RunState(row["stage"]): int(row["attempts"]) for row in rows}
        usage = self.repo.run_usage(self._run_id)
        self.requests, self.tool_calls = usage["model_requests"], usage["tool_calls"]
        self.prompt_tokens, self.completion_tokens = None, None  # earlier attempts: unknown mix
        reusable: dict[RunState, dict[str, Any]] = {}
        reused: list[str] = []
        for stage in STAGES:
            latest = self.attempts.get(stage, 0)
            if latest == 0:
                break
            name = f"stages/{stage.value.lower()}-{latest}"
            if name not in self.artifacts.hashes:
                break
            saved = self.artifacts.read(name)
            if not (saved["result"]["completed"] and saved["payload"] is not None):
                break
            reusable[stage] = saved["payload"]
            reused.append(f"{stage.value.lower()} (attempt {latest})")
        interrupted = [
            f"{item.stage.value.lower()} ({item.exit_reason})"
            for item in history
            if not item.completed
        ]
        self.warnings.append(
            f"recovered: reused {', '.join(reused) or 'no stages'}; interrupted attempts kept in "
            f"history: {', '.join(interrupted) or 'none'}"
        )
        return reusable

    def _refreeze(self, snapshot_id: str) -> None:
        """Re-open the run's own frozen snapshot; evidence must still match it."""
        assert self.record is not None
        manifest = self.repo.get_snapshot(snapshot_id)
        if manifest is None:
            raise _Stop(
                RunState.FAILED, f"snapshot {snapshot_id} is missing", ErrorCode.INTEGRITY_ERROR
            )
        self.evidence = self.loader(self.record.request)
        try:
            self.view = build_view(
                manifest,
                self.evidence.documents,
                self.evidence.spans,
                dict(self.evidence.document_texts),
            )
        except EpisAlphaError as error:
            raise _Stop(
                RunState.FAILED, f"cannot re-open snapshot: {error}", ErrorCode.INTEGRITY_ERROR
            ) from None

    def _check_cancel(self) -> None:
        assert self.record is not None
        if cancel_requested(self.repo, self.record.request.run_id):
            raise _Stop(RunState.CANCELLED, "cancellation requested")

    # --- 2. freeze ----------------------------------------------------------------------------

    def _freeze(self) -> None:
        assert self.record is not None
        request = self.record.request
        with span("snapshot.freeze", SpanKind.CHAIN) as current:
            self.evidence = self.loader(request)
            evidence = self.evidence
            manifest = build_snapshot(
                snapshot_id=f"snapshot.{request.run_id}",
                instrument_ids=[request.instrument_id],
                research_cutoff=request.research_cutoff,
                research_mode=request.research_mode,
                documents=evidence.documents,
                spans=evidence.spans,
                claims=evidence.claims,
                relations=evidence.relations,
                source_completeness=evidence.source_completeness,
                source_version=evidence.source_version,
                frozen_at=self._now(),
            )
            self.view = build_view(
                manifest, evidence.documents, evidence.spans, dict(evidence.document_texts)
            )
            with transaction(self.repo.connection):
                self.repo.save_all(
                    [
                        *evidence.entities,
                        *evidence.instruments,
                        *(d for d in evidence.documents if d.document_id in manifest.document_ids),
                        *(s for s in evidence.spans if s.span_id in manifest.permitted_span_ids),
                    ]
                )
                self.repo.save_snapshot(manifest)
            # Texts go to the content store under their own hash, so a snapshot can be re-read
            # later (replay, snapshot reruns) without re-fetching anything.
            for document in evidence.documents:
                text = evidence.document_texts.get(document.document_id)
                if document.document_id in manifest.document_ids and text is not None:
                    if self.objects.put(text.encode("utf-8")) != document.parsed_text_hash:
                        self.warnings.append(
                            f"document {document.document_id} text does not match its "
                            "parsed_text_hash"
                        )
            annotate(
                current,
                **{
                    "episalpha.snapshot_id": manifest.snapshot_id,
                    "episalpha.snapshot_hash": manifest.snapshot_hash,
                    "episalpha.documents": len(manifest.document_ids),
                    "episalpha.spans": len(manifest.permitted_span_ids),
                    "episalpha.claims": len(manifest.permitted_claim_ids),
                    "episalpha.missing_sources": list(self.view.missing_sources),
                },
            )
        self.artifacts.write("manifest", manifest.model_dump(mode="json"))
        self._move(RunState.SNAPSHOT_FROZEN, snapshot_id=manifest.snapshot_id)
        if not self.view.has_essential_evidence:
            if self.view.missing_sources:
                raise _Stop(
                    RunState.FAILED,
                    f"sources failed while freezing: {list(self.view.missing_sources)}; this is "
                    "not an absence of evidence",
                    ErrorCode.SOURCE_FAILED,
                )
            self.missing.append("No eligible evidence documents exist at this cutoff.")
            raise _Stop(
                RunState.ABSTAINED,
                "essential evidence missing: no eligible documents at the research cutoff. Next "
                "inquiry: ingest the filings for this instrument and cutoff.",
            )

    # --- 3-6. stages -----------------------------------------------------------------------------

    def _context(self, stage: RunState) -> RuntimeContext:
        assert self.record is not None and self.view is not None
        budgets = self.record.request.budgets
        elapsed = int(time.monotonic() - self.started)
        return RuntimeContext(
            run_id=self.record.request.run_id,
            snapshot=self.view.manifest,
            stage=stage,
            validated_claim_ids=tuple(self.claims),
            validated_hypothesis_ids=tuple(self.hypotheses),
            remaining_model_requests=max(0, budgets.max_model_requests - self.requests),
            remaining_tool_calls=max(0, budgets.max_tool_calls - self.tool_calls),
            remaining_wall_time_seconds=max(0, budgets.run_wall_time_seconds - elapsed),
        )

    def _stage(self, stage: RunState, runtime: ResearchRuntimePort) -> None:
        assert self.record is not None
        if self.record.state is not stage:
            self._move(stage)
        payload = self._attempt(stage, runtime)
        try:
            self._accept(stage, payload)
        except _Invalid as problem:
            if self.repairs_left <= 0:
                raise _Stop(
                    RunState.REJECTED,
                    f"{stage.value.lower()} output invalid: {problem}",
                    ErrorCode.INVALID_OUTPUT,
                    via_validation=True,
                ) from None
            self.repairs_left -= 1
            self.repair_note = str(problem)
            with span("repair.attempt", SpanKind.CHAIN, **{"episalpha.stage": stage.value}):
                payload = self._attempt(stage, runtime)
            self.repair_note = ""
            try:
                self._accept(stage, payload)
            except _Invalid as again:
                raise _Stop(
                    RunState.REJECTED,
                    f"{stage.value.lower()} output invalid after one repair: {again}",
                    ErrorCode.INVALID_OUTPUT,
                    via_validation=True,
                ) from None
            self.warnings.append(f"{stage.value.lower()} output repaired once: {problem}")

    def _attempt(self, stage: RunState, runtime: ResearchRuntimePort) -> dict[str, Any] | None:
        """Run one stage attempt, persist it, and return its payload or end the run."""
        assert self.record is not None
        self._check_cancel()
        context = self._context(stage)
        if context.remaining_wall_time_seconds <= 0:
            raise _Stop(RunState.TIMED_OUT, "run wall time spent", ErrorCode.BUDGET_EXCEEDED)
        attempt = self.attempts.get(stage, 0) + 1
        self.attempts[stage] = attempt
        started = self._now()
        with transaction(self.repo.connection):
            # Recorded before the model is called: if the process dies mid-call, this attempt
            # stays in history as incomplete, never silently missing (plan section 3.7).
            self.repo.save_stage_result(
                self.record.request.run_id,
                attempt,
                StageResult(
                    stage=stage,
                    completed=False,
                    exit_reason="started",
                    started_at=started,
                    ended_at=started,
                ),
            )
        with span(
            f"stage.{stage.value.lower()}",
            SpanKind.AGENT,
            **{"episalpha.stage": stage.value, "episalpha.attempt": attempt},
        ) as current:
            result = runtime.run_stage(stage, context)
            annotate(
                current,
                **{
                    "episalpha.exit_reason": result.exit_reason,
                    "episalpha.completed": result.completed,
                    "episalpha.model_requests": result.usage.model_requests,
                },
            )
        with transaction(self.repo.connection):
            self.repo.save_stage_result(self.record.request.run_id, attempt, result)
        self.stages.append(result)
        self.requests += result.usage.model_requests
        self.tool_calls += result.usage.tool_calls
        self.prompt_tokens = _add(self.prompt_tokens, result.usage.prompt_tokens)
        self.completion_tokens = _add(self.completion_tokens, result.usage.completion_tokens)
        payload: dict[str, Any] | None = None
        if result.candidate_payload_hash is not None:
            payload = json.loads(self.objects.get(result.candidate_payload_hash))
        self.artifacts.write(
            f"stages/{stage.value.lower()}-{attempt}",
            {"result": result.model_dump(mode="json"), "payload": payload},
        )
        reason = _exit_reason(result.exit_reason)
        if reason in _EXIT_TERMINALS:
            state, code = _EXIT_TERMINALS[reason]
            raise _Stop(state, f"{stage.value.lower()}: {result.exit_reason}", code)
        if reason is ExitReason.PARTIAL:
            raise _Stop(
                RunState.PARTIAL,
                f"{stage.value.lower()} ended partially: {result.exit_reason}",
                via_validation=True,
            )
        if not result.completed or payload is None:
            return None
        return payload

    def _accept(self, stage: RunState, payload: dict[str, Any] | None) -> None:
        if payload is None:
            raise _Invalid("the stage produced no valid submission")
        try:
            candidate = parse_candidate(stage, payload)
        except ValidationError as error:
            first = error.errors()[0]
            where = ".".join(str(part) for part in first["loc"])
            raise _Invalid(f"{where}: {first['msg']}") from None
        if isinstance(candidate, ResearchCandidate):
            self._accept_research(candidate)
        elif isinstance(candidate, CritiqueCandidate):
            self._accept_critique(candidate)
        elif isinstance(candidate, ThesisCandidate):
            self._accept_thesis(candidate)

    def _canonical_claim(self, item: CandidateClaim, attribution: str | None = None) -> Claim:
        assert self.record is not None
        request = self.record.request
        try:
            return Claim(
                claim_id=f"{request.run_id}.{item.key}",
                statement=item.statement,
                subject_ids=(request.instrument_id,),
                attribution=attribution or item.attribution,
                epistemic_status=item.epistemic_status,
                span_ids=item.span_ids,
                derivation=Derivation(**item.derivation.model_dump()) if item.derivation else None,
                numeric_fact=NumericFact(**item.numeric_fact.model_dump())
                if item.numeric_fact
                else None,
                created_at=self._now(),
                run_id=request.run_id,
            )
        except ValidationError as error:
            raise _Invalid(f"claim {item.key!r}: {error.errors()[0]['msg']}") from None

    def _fresh(self, record_id: str) -> None:
        """A model may never take over an ID that already exists anywhere."""
        if self.repo.node_kind(record_id) is not None or record_id in self.claims:
            raise _Invalid(f"ID {record_id!r} already exists; a canonical ID is never reused")

    def _check(
        self,
        claims: Sequence[Claim],
        hypotheses: Sequence[Hypothesis] = (),
        relations: Sequence[Relation] = (),
    ) -> None:
        assert self.view is not None
        report = validate(
            RecordSet(
                documents=list(self.view.documents.values()),
                spans=list(self.view.spans.values()),
                claims=[*self.evidence.claims, *self.claims.values(), *claims],
                hypotheses=[*self.hypotheses.values(), *hypotheses],
                relations=[*self.relations, *relations],
                instruments=list(self.evidence.instruments),
                entities=list(self.evidence.entities),
                document_texts=dict(self.view.document_texts),
            ),
            run_id=self._run_id,
        )
        failures = failed_checks(report)
        if failures:
            raise _Invalid("; ".join(f"{f.check}: {f.detail}" for f in failures[:5]))

    @property
    def _run_id(self) -> str:
        assert self.record is not None
        return self.record.request.run_id

    def _accept_research(self, candidate: ResearchCandidate) -> None:
        claims = [self._canonical_claim(item) for item in candidate.claims]
        hypotheses = []
        for item in candidate.hypotheses:
            try:
                hypotheses.append(
                    Hypothesis(
                        hypothesis_id=f"{self._run_id}.{item.key}",
                        mechanism=item.mechanism,
                        assumptions=item.assumptions,
                        supporting_claim_ids=item.supporting_claim_ids,
                        opposing_claim_ids=item.opposing_claim_ids,
                        falsification_condition=item.falsification_condition,
                        horizon_trading_days=item.horizon_trading_days,
                        created_at=self._now(),
                    )
                )
            except ValidationError as error:
                raise _Invalid(f"hypothesis {item.key!r}: {error.errors()[0]['msg']}") from None
        for record_id in [c.claim_id for c in claims] + [h.hypothesis_id for h in hypotheses]:
            self._fresh(record_id)
        self._check(claims, hypotheses)
        self.claims.update({c.claim_id: c for c in claims})
        self.hypotheses.update({h.hypothesis_id: h for h in hypotheses})

    def _accept_critique(self, candidate: CritiqueCandidate) -> None:
        counters = [
            self._canonical_claim(item, attribution=f"critic: {item.attribution}")
            for item in candidate.counter_claims
        ]
        for item in counters:
            self._fresh(item.claim_id)
        relations = [
            Relation(
                relation_id=f"{self._run_id}.r{index}",
                predicate=RelationPredicate.CONTRADICTS,
                source_id=item.contradicted_by_claim_id,
                target_id=item.claim_id,
                evidence_span_ids=item.span_ids,
                epistemic_status=EpistemicStatus.REPORTED
                if item.span_ids
                else EpistemicStatus.HYPOTHESIZED,
                created_at=self._now(),
                run_id=self._run_id,
            )
            for index, item in enumerate(candidate.contradictions, start=len(self.relations) + 1)
        ]
        self._check(counters, relations=relations)
        self.claims.update({c.claim_id: c for c in counters})
        self.relations.extend(relations)
        self.missing.extend(candidate.missing_information)
        self.critique = {
            "contradictions": [r.model_dump(mode="json") for r in relations],
            "missing_information": list(candidate.missing_information),
        }

    def _accept_thesis(self, candidate: ThesisCandidate) -> None:
        assert self.record is not None and self.view is not None
        request = self.record.request
        horizons = [h.horizon_trading_days for h in self.hypotheses.values()]
        missing = list(dict.fromkeys([*self.missing, *candidate.missing_information]))
        try:
            thesis = Thesis(
                thesis_id=f"{request.run_id}.thesis",
                run_id=request.run_id,
                instrument_id=request.instrument_id,
                research_cutoff=request.research_cutoff,
                research_mode=request.research_mode,
                horizon_trading_days=max(horizons, default=DEFAULT_HORIZON_TRADING_DAYS),
                stance=candidate.stance,
                assertions=tuple(
                    ThesisAssertion(
                        assertion_id=f"{request.run_id}.a{index}",
                        section=item.section,
                        text=item.text,
                        claim_ids=item.claim_ids,
                        hypothesis_ids=item.hypothesis_ids,
                    )
                    for index, item in enumerate(candidate.assertions, start=1)
                ),
                missing_information=tuple(missing),
                next_inquiry=candidate.next_inquiry,
                snapshot_id=self.view.manifest.snapshot_id,
                snapshot_hash=self.view.manifest.snapshot_hash,
                harness_id=request.harness_id,
                model_identifier=str(getattr(self._runtime, "model_id", "unknown")),
                created_at=self._now(),
            )
        except ValidationError as error:
            raise _Invalid(f"thesis: {error.errors()[0]['msg']}") from None
        self._fresh(thesis.thesis_id)
        report = self._report(thesis)
        failures = failed_checks(report)
        if failures:
            raise _Invalid("; ".join(f"{f.check}: {f.detail}" for f in failures[:5]))
        self.thesis = thesis

    # --- 7. validation ---------------------------------------------------------------------------

    def _report(self, thesis: Thesis | None, partial: bool = False) -> ValidationReport:
        assert self.view is not None
        return validate(
            RecordSet(
                documents=list(self.view.documents.values()),
                spans=list(self.view.spans.values()),
                claims=[*self.evidence.claims, *self.claims.values()],
                hypotheses=list(self.hypotheses.values()),
                relations=[*self.relations],
                instruments=list(self.evidence.instruments),
                entities=list(self.evidence.entities),
                theses=[thesis] if thesis is not None else [],
                document_texts=dict(self.view.document_texts),
            ),
            run_id=self._run_id,
            thesis=thesis,
            partial=partial,
        )

    def _validated(self, partial: bool) -> ValidationReport:
        with span("validation", SpanKind.EVALUATOR) as current:
            report = self._report(self.thesis, partial=partial)
            for check in report.checks:
                event(
                    "validation.check", check=check.check, passed=check.passed, detail=check.detail
                )
            annotate(
                current,
                **{
                    "episalpha.disposition": report.disposition.value,
                    "episalpha.failed_checks": len(failed_checks(report)),
                    "episalpha.unresolved_reviews": len(report.unresolved_semantic_reviews),
                },
            )
        self.artifacts.write("validation", report.model_dump(mode="json"))
        return report

    def _validate_and_finish(self, runtime: ResearchRuntimePort) -> None:
        assert self.thesis is not None
        self._move(RunState.VALIDATING)
        report = self._validated(partial=False)
        if not report.structurally_valid:
            failures = "; ".join(f"{f.check}: {f.detail}" for f in failed_checks(report)[:5])
            raise _Stop(
                RunState.REJECTED, f"final validation failed: {failures}", ErrorCode.INVALID_OUTPUT
            )
        if self.thesis.stance.value == "abstain":
            raise _Stop(
                RunState.ABSTAINED,
                "the synthesizer abstained: the validated evidence "
                f"does not answer the question. Next inquiry: {self.thesis.next_inquiry}",
            )
        raise _Stop(RunState.RESEARCH_COMPLETED, "research completed and validated")

    # --- 8. persist and declare --------------------------------------------------------------

    _runtime: ResearchRuntimePort | None = None

    def _finish(self, stop: _Stop, runtime: ResearchRuntimePort) -> None:
        assert self.record is not None
        state = stop.state
        if stop.via_validation and self.record.state in (
            RunState.RESEARCHING,
            RunState.CRITIQUING,
            RunState.SYNTHESIZING,
        ):
            self._move(RunState.VALIDATING)
            report = self._validated(partial=state is RunState.PARTIAL)
            if state is RunState.PARTIAL and not report.structurally_valid:
                state, stop.code = RunState.REJECTED, ErrorCode.INVALID_OUTPUT
        keep_thesis = state in (RunState.RESEARCH_COMPLETED, RunState.ABSTAINED)
        thesis = self.thesis if keep_thesis else None
        persisted = state not in (RunState.REJECTED,)
        with span("run.persist", SpanKind.CHAIN) as current:
            records: list[Any] = []
            if persisted:
                records = [*self.claims.values(), *self.hypotheses.values(), *self.relations]
                if thesis is not None:
                    records.append(thesis)
            with transaction(self.repo.connection):
                self.repo.save_all(records)
            self.artifacts.write(
                "records",
                {
                    "claims": [c.model_dump(mode="json") for c in self.claims.values()],
                    "hypotheses": [h.model_dump(mode="json") for h in self.hypotheses.values()],
                    "relations": [r.model_dump(mode="json") for r in self.relations],
                    "persisted": persisted,
                },
            )
            if thesis is not None:
                self.artifacts.write("thesis", thesis.model_dump(mode="json"))
            self.artifacts.write(
                "proposals",
                [p.model_dump(mode="json") for p in getattr(runtime, "proposals", [])],
            )
            harness = getattr(runtime, "harness", None)
            assert self.view is not None or state in (RunState.CANCELLED, RunState.FAILED)
            self.artifacts.write_index(
                run_id=self._run_id,
                trace_id=self.trace_id,
                runtime=self.record.request.runtime_mode.value,
                model_identifier=str(getattr(runtime, "model_id", "unknown")),
                served_by=sorted(set(getattr(runtime, "served_by", ()))),
                snapshot_id=self.view.manifest.snapshot_id if self.view else None,
                snapshot_hash=self.view.manifest.snapshot_hash if self.view else None,
                harness_id=self.record.request.harness_id,
                harness_hash=getattr(harness, "harness_hash", None),
                skill_set_hash=getattr(harness, "skill_set_hash", None),
                state=state.value,
                **self.lineage,
            )
            annotate(current, **{"episalpha.records": len(records), "episalpha.state": state.value})
        validation = None
        if self.record.state is RunState.VALIDATING or state in (
            RunState.RESEARCH_COMPLETED,
            RunState.ABSTAINED,
        ):
            validation = self._report(thesis, partial=state is RunState.PARTIAL)
        self._move(
            state,
            reason=stop.reason[:2000],
            error_code=stop.code,
            thesis_id=thesis.thesis_id if thesis is not None else None,
            validation_report=validation,
            warnings=tuple(self.warnings),
            usage=Usage(
                model_requests=self.requests,
                tool_calls=self.tool_calls,
                prompt_tokens=self.prompt_tokens,
                completion_tokens=self.completion_tokens,
            ),
            stages=tuple(self.stages),
            ended_at=self._now(),
        )
        with transaction(self.repo.connection):
            self.repo.connection.execute("DELETE FROM run_lease WHERE run_id = ?", (self._run_id,))

    def _move(self, state: RunState, **updates: Any) -> None:
        assert self.record is not None
        self.record.transition(state)
        data = {**self.record.model_dump(), **updates, "state": state}
        self.record = RunRecord.model_validate(data)
        with transaction(self.repo.connection):
            self.repo.update_run(self.record)


def _add(total: int | None, value: int | None) -> int | None:
    return total + value if total is not None and value is not None else None
