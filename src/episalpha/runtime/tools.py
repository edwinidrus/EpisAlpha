"""Snapshot-bound typed tools (plan M3-T01; amendments A5, A6, A8, A13).

Every tool here is read-only except ``propose_skill``, which only appends a proposal to this
run's in-memory list, as data. Each tool:

- takes its cutoff and snapshot from the immutable :class:`RuntimeContext`, never from an
  argument; no tool accepts a date, path, URL or SQL;
- answers only from records the frozen manifest permits, plus current-run records the host has
  already validated; anything else is ``NOT_AUTHORIZED``;
- counts against the run's tool-call budget and refuses an oversize result with
  ``BUDGET_EXCEEDED`` instead of truncating it;
- returns a hashed :class:`ToolResult` and emits one ``tool.<name>`` span (``search_evidence``
  is a ``RETRIEVER``). Arguments and results are content attributes, so they reach only the
  local Phoenix; the JSONL fallback keeps their hashes and sizes.

The worker reaches these over MCP (M3-T03). Arithmetic stays host-side: ``compute_derivation``
runs the M1-T05 registry and the model never supplies a computed value (A8).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Iterable, Sequence
from datetime import timedelta
from typing import Any

from pydantic import Field

from episalpha.connectors.prices import PriceSeries
from episalpha.contracts.errors import EpisAlphaError, ErrorCode
from episalpha.contracts.knowledge import (
    Claim,
    Contract,
    Derivation,
    Hypothesis,
    Identifier,
    Instrument,
    NumericFact,
    Relation,
    RelationPredicate,
)
from episalpha.contracts.research import RuntimeContext
from episalpha.evidence.snapshots import SnapshotView
from episalpha.observability import SpanKind, annotate, span
from episalpha.research.derivations import recompute
from episalpha.runtime.port import ToolResult
from episalpha.settings import Limits

TOOL_NAMES = (
    "resolve_instrument",
    "search_evidence",
    "get_evidence_span",
    "get_market_context",
    "get_support_and_contradictions",
    "get_numeric_facts",
    "compute_derivation",
    "propose_skill",
)


class SkillProposal(Contract):
    """A candidate procedure the model suggests. Data only; screening and promotion are M8."""

    proposal_id: Identifier
    run_id: Identifier
    title: str = Field(min_length=1, max_length=200)
    when_to_use: str = Field(min_length=1)
    procedure_steps: tuple[str, ...] = Field(min_length=1)
    rationale: str = Field(min_length=1)
    evidence_span_ids: tuple[Identifier, ...] = ()


class _Refused(Exception):
    """A typed tool refusal raised inside a handler."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


_WORD = re.compile(r"[a-z0-9][a-z0-9.%$-]*[a-z0-9%]|[a-z0-9]")
_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "from",
        "was",
        "were",
        "are",
        "did",
        "does",
        "what",
        "which",
        "about",
        "its",
        "has",
        "had",
        "have",
        "any",
        "into",
        "than",
    }
)


def _terms(text: str) -> set[str]:
    """Lowercase words of three or more characters, minus a few stopwords."""
    return {
        word for word in _WORD.findall(text.casefold()) if len(word) >= 3 and word not in _STOPWORDS
    }


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()


def _numeric(claim: Claim, fact: NumericFact) -> dict[str, Any]:
    return {
        "claim_id": claim.claim_id,
        "metric": fact.metric,
        "value": str(fact.value),
        "unit": fact.unit,
        "period_start": fact.period_start.isoformat(),
        "period_end": fact.period_end.isoformat(),
        "accounting_basis": fact.accounting_basis,
        "source_context": fact.source_context,
    }


class ToolHost:
    """The tools of one run stage, bound to its frozen snapshot and validated records.

    ``claims``, ``relations``, ``instruments`` and ``hypotheses`` may be supersets; only the
    ones the manifest permits (or ``context`` lists as validated current-run records) are ever
    visible. ``market`` is the snapshot's frozen price context, if any.
    """

    def __init__(
        self,
        view: SnapshotView,
        context: RuntimeContext,
        limits: Limits,
        *,
        claims: Iterable[Claim] = (),
        relations: Iterable[Relation] = (),
        instruments: Iterable[Instrument] = (),
        hypotheses: Iterable[Hypothesis] = (),
        market: PriceSeries | None = None,
        price_source_id: str | None = None,
    ) -> None:
        manifest = context.snapshot
        self.view = view
        self.context = context
        self.limits = limits
        visible_claims = set(manifest.permitted_claim_ids) | set(context.validated_claim_ids)
        self._claims = {c.claim_id: c for c in claims if c.claim_id in visible_claims}
        self._relations = [r for r in relations if r.relation_id in manifest.permitted_relation_ids]
        self._instruments = {
            i.instrument_id: i for i in instruments if i.instrument_id in manifest.instrument_ids
        }
        self._hypotheses = {
            h.hypothesis_id: h
            for h in hypotheses
            if h.hypothesis_id in context.validated_hypothesis_ids
        }
        self._market = market
        self._price_source_id = price_source_id
        self._calls_left = context.remaining_tool_calls
        self.tool_calls_used = 0
        self.result_hashes: list[str] = []
        self._proposals: list[SkillProposal] = []

    @property
    def proposals(self) -> tuple[SkillProposal, ...]:
        return tuple(self._proposals)

    # --- the shared envelope ---------------------------------------------------------------

    def _call(
        self,
        name: str,
        arguments: dict[str, Any],
        handler: Callable[[], dict[str, Any]],
        kind: SpanKind = SpanKind.TOOL,
    ) -> ToolResult:
        encoded_arguments = _canonical(arguments)
        with span(
            f"tool.{name}",
            kind,
            **{
                "tool.name": name,
                "tool.parameters": encoded_arguments.decode(),
                "episalpha.args_hash": hashlib.sha256(encoded_arguments).hexdigest(),
            },
        ) as current:
            if self._calls_left <= 0:
                result = self._result(
                    False,
                    {"error": f"tool-call budget of {self.context.remaining_tool_calls} is spent"},
                    ErrorCode.BUDGET_EXCEEDED,
                )
            else:
                self._calls_left -= 1
                self.tool_calls_used += 1
                result = self._execute(handler)
            if kind is SpanKind.RETRIEVER and result.ok:
                for index, hit in enumerate(result.payload.get("hits", [])):
                    annotate(
                        current,
                        **{
                            f"retrieval.documents.{index}.document.id": hit["span_id"],
                            f"retrieval.documents.{index}.document.content": hit["quote"],
                        },
                    )
            annotate(
                current,
                **{
                    "output.value": _canonical(result.payload).decode(),
                    "episalpha.result_hash": result.result_hash,
                    "episalpha.bytes": result.bytes,
                    "episalpha.error_code": result.error_code.value if result.error_code else "",
                },
            )
            self.result_hashes.append(result.result_hash)
            return result

    def _execute(self, handler: Callable[[], dict[str, Any]]) -> ToolResult:
        try:
            payload = handler()
        except _Refused as refusal:
            return self._result(False, {"error": str(refusal)}, refusal.code)
        except EpisAlphaError as error:
            return self._result(False, {"error": str(error)}, error.code)
        result = self._result(True, payload, None)
        if result.bytes > self.limits.max_tool_result_bytes:
            return self._result(
                False,
                {
                    "error": f"result of {result.bytes} bytes exceeds max_tool_result_bytes "
                    f"({self.limits.max_tool_result_bytes}); narrow the request"
                },
                ErrorCode.BUDGET_EXCEEDED,
            )
        return result

    @staticmethod
    def _result(ok: bool, payload: dict[str, Any], code: ErrorCode | None) -> ToolResult:
        envelope = _canonical(
            {"ok": ok, "payload": payload, "error_code": code.value if code else None}
        )
        return ToolResult(
            ok=ok,
            payload=payload,
            error_code=code,
            result_hash=hashlib.sha256(envelope).hexdigest(),
            bytes=len(envelope),
        )

    # --- scope helpers ---------------------------------------------------------------------

    def _instrument(self, instrument_id: str) -> Instrument | str:
        if instrument_id not in self.context.snapshot.instrument_ids:
            raise _Refused(
                ErrorCode.NOT_AUTHORIZED, f"instrument {instrument_id!r} is not in this snapshot"
            )
        return self._instruments.get(instrument_id, instrument_id)

    def _claim(self, claim_id: str) -> Claim:
        claim = self._claims.get(claim_id)
        if claim is None:
            raise _Refused(
                ErrorCode.NOT_AUTHORIZED,
                f"claim {claim_id!r} is neither in the snapshot nor a validated current-run record",
            )
        return claim

    # --- the tools -------------------------------------------------------------------------

    def resolve_instrument(self, ticker: str) -> ToolResult:
        def handler() -> dict[str, Any]:
            cutoff = self.context.research_cutoff
            wanted = ticker.strip().upper()
            for instrument in self._instruments.values():
                for alias in instrument.ticker_aliases:
                    valid = alias.valid_from <= cutoff and (
                        alias.valid_to is None or cutoff < alias.valid_to
                    )
                    if valid and alias.ticker.upper() == wanted:
                        return {"instrument_id": instrument.instrument_id}
            raise _Refused(
                ErrorCode.NO_DATA, f"no instrument in this snapshot had ticker {ticker!r} then"
            )

        return self._call("resolve_instrument", {"ticker": ticker}, handler)

    def search_evidence(self, query: str, limit: int) -> ToolResult:
        def handler() -> dict[str, Any]:
            if not query.strip():
                raise _Refused(ErrorCode.INVALID_REQUEST, "query must not be empty")
            applied = max(1, min(limit, self.limits.max_evidence_search_hits))
            wanted = _terms(query)
            if not wanted:
                raise _Refused(ErrorCode.INVALID_REQUEST, "query has no searchable words")
            # ponytail: keyword overlap, not semantic search. Each span scores the number of
            # distinct query words it contains; ties keep document order. Add stemming or an
            # index only when real snapshots outgrow a linear scan.
            scored = []
            for span_id in self.context.snapshot.permitted_span_ids:
                found = self.view.span(span_id)
                score = len(wanted & _terms(found.exact_quote))
                if score:
                    scored.append((-score, found.document_id, found.start_offset, found))
            hits = [entry[3] for entry in sorted(scored, key=lambda entry: entry[:3])[:applied]]
            return {
                "limit_applied": applied,
                "hits": [
                    {
                        "span_id": hit.span_id,
                        "document_id": hit.document_id,
                        "quote": hit.exact_quote,
                        "locator": hit.section_locator,
                    }
                    for hit in hits
                ],
            }

        return self._call(
            "search_evidence", {"query": query, "limit": limit}, handler, SpanKind.RETRIEVER
        )

    def get_evidence_span(self, span_id: str) -> ToolResult:
        def handler() -> dict[str, Any]:
            found = self.view.span(span_id)
            document = self.view.document(found.document_id)
            return {
                "span_id": found.span_id,
                "document_id": found.document_id,
                "quote": found.exact_quote,
                "locator": found.section_locator,
                "start_offset": found.start_offset,
                "end_offset": found.end_offset,
                "source_uri": document.source_uri,
                "published_at": document.published_at.isoformat()
                if document.published_at
                else None,
            }

        return self._call("get_evidence_span", {"span_id": span_id}, handler)

    def get_market_context(self, instrument_id: str) -> ToolResult:
        def handler() -> dict[str, Any]:
            self._instrument(instrument_id)
            market = self._market
            if market is None or market.instrument_id != instrument_id:
                if self._price_source_id in self.view.missing_sources:
                    raise _Refused(
                        ErrorCode.SOURCE_FAILED,
                        "the price source failed when the snapshot was frozen; this is not an "
                        "absence of prices",
                    )
                raise _Refused(ErrorCode.NO_DATA, f"no price context for {instrument_id!r}")
            # ponytail: a close dated on the cutoff day is excluded, because a midnight-UTC
            # cutoff precedes that day's close. Add an exchange-close clock if intraday cutoffs
            # ever appear.
            series = market.as_of(self.context.research_cutoff.date() - timedelta(days=1))
            if series is None:
                raise _Refused(ErrorCode.NO_DATA, "no close strictly before the cutoff")
            first, last = series.points[0], series.points[-1]
            multi_day: str | None = None
            reason = ""
            if series.is_adjusted and first.trade_date != last.trade_date:
                multi_day = str(series.simple_return(first.trade_date, last.trade_date))
            elif not series.is_adjusted:
                reason = (
                    "unadjusted close: a split or dividend would manufacture a false return, so "
                    "no multi-day return is computed (A6)"
                )
            return {
                "instrument_id": instrument_id,
                "source_id": series.source_id,
                "currency": series.currency,
                "adjustment_basis": series.adjustment_basis.value,
                "points": [
                    {"date": p.trade_date.isoformat(), "close": str(p.close)} for p in series.points
                ],
                "latest_close": str(last.close),
                "multi_day_return": multi_day,
                "multi_day_return_reason": reason,
            }

        return self._call("get_market_context", {"instrument_id": instrument_id}, handler)

    def get_support_and_contradictions(self, record_id: str) -> ToolResult:
        def handler() -> dict[str, Any]:
            supports: list[dict[str, Any]] = []
            contradicts: list[dict[str, Any]] = []
            if record_id in self._hypotheses:
                hypothesis = self._hypotheses[record_id]
                supports += [
                    {"relation_id": None, "other_id": c} for c in hypothesis.supporting_claim_ids
                ]
                contradicts += [
                    {"relation_id": None, "other_id": c} for c in hypothesis.opposing_claim_ids
                ]
            else:
                self._claim(record_id)
            for relation in self._relations:
                if record_id not in (relation.source_id, relation.target_id):
                    continue
                outgoing = relation.source_id == record_id
                other = relation.target_id if outgoing else relation.source_id
                entry = {"relation_id": relation.relation_id, "other_id": other}
                if relation.predicate is RelationPredicate.SUPPORTS:
                    supports.append(entry)
                elif relation.predicate is RelationPredicate.CONTRADICTS:
                    contradicts.append(entry)
            return {"record_id": record_id, "supports": supports, "contradicts": contradicts}

        return self._call("get_support_and_contradictions", {"record_id": record_id}, handler)

    def get_numeric_facts(self, instrument_id: str, concepts: Sequence[str]) -> ToolResult:
        def handler() -> dict[str, Any]:
            self._instrument(instrument_id)
            wanted = set(concepts)
            facts = [
                _numeric(claim, claim.numeric_fact)
                for claim in sorted(self._claims.values(), key=lambda c: c.claim_id)
                if claim.numeric_fact is not None
                and instrument_id in claim.subject_ids
                and (not wanted or claim.numeric_fact.metric in wanted)
            ]
            if not facts:
                raise _Refused(ErrorCode.NO_DATA, "no numeric facts match in this snapshot")
            return {"instrument_id": instrument_id, "facts": facts}

        return self._call(
            "get_numeric_facts",
            {"instrument_id": instrument_id, "concepts": list(concepts)},
            handler,
        )

    def compute_derivation(
        self, method: str, method_version: str, input_claim_ids: Sequence[str]
    ) -> ToolResult:
        def handler() -> dict[str, Any]:
            inputs = [self._claim(claim_id) for claim_id in input_claim_ids]
            facts = []
            for claim in inputs:
                if claim.numeric_fact is None:
                    raise _Refused(
                        ErrorCode.INVALID_REQUEST, f"claim {claim.claim_id!r} carries no number"
                    )
                facts.append(claim.numeric_fact)
            try:
                derivation = Derivation(
                    method=method,
                    method_version=method_version,
                    input_claim_ids=tuple(input_claim_ids),
                )
            except ValueError as error:
                raise _Refused(ErrorCode.INVALID_REQUEST, str(error)) from None
            value, unit = recompute(derivation, facts)
            return {
                "value": str(value),
                "unit": unit,
                "method": method,
                "method_version": method_version,
                "input_claim_ids": list(input_claim_ids),
            }

        return self._call(
            "compute_derivation",
            {
                "method": method,
                "method_version": method_version,
                "input_claim_ids": list(input_claim_ids),
            },
            handler,
        )

    def propose_skill(
        self,
        title: str,
        when_to_use: str,
        procedure_steps: Sequence[str],
        rationale: str,
        evidence_span_ids: Sequence[str],
    ) -> ToolResult:
        arguments = {
            "title": title,
            "when_to_use": when_to_use,
            "procedure_steps": list(procedure_steps),
            "rationale": rationale,
            "evidence_span_ids": list(evidence_span_ids),
        }

        def handler() -> dict[str, Any]:
            if len(self._proposals) >= self.limits.max_skill_proposals:
                raise _Refused(
                    ErrorCode.BUDGET_EXCEEDED,
                    f"at most {self.limits.max_skill_proposals} skill proposals per run",
                )
            size = len(_canonical(arguments))
            if size > self.limits.max_skill_proposal_bytes:
                raise _Refused(
                    ErrorCode.INVALID_REQUEST,
                    f"proposal is {size} bytes; the limit is "
                    f"{self.limits.max_skill_proposal_bytes}",
                )
            for span_id in evidence_span_ids:
                if span_id not in self.context.snapshot.permitted_span_ids:
                    raise _Refused(
                        ErrorCode.NOT_AUTHORIZED, f"span {span_id!r} is not in this snapshot"
                    )
            digest = hashlib.sha256(_canonical([self.context.run_id, arguments])).hexdigest()
            try:
                proposal = SkillProposal(
                    proposal_id=f"proposal-{len(self._proposals) + 1}-{digest[:12]}",
                    run_id=self.context.run_id,
                    title=title,
                    when_to_use=when_to_use,
                    procedure_steps=tuple(procedure_steps),
                    rationale=rationale,
                    evidence_span_ids=tuple(evidence_span_ids),
                )
            except ValueError as error:
                raise _Refused(ErrorCode.INVALID_REQUEST, str(error)) from None
            self._proposals.append(proposal)
            return {"proposal_id": proposal.proposal_id}

        return self._call("propose_skill", arguments, handler)
