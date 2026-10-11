"""Deterministic structural validation (plan section M1-T04).

What this module can decide: does every reference resolve, is every relation endpoint of an
allowed kind, does every quoted passage match the stored text character for character, does
every material assertion point at something.

What it deliberately cannot decide: whether a claim *follows from* the passage it cites. An
exact quotation match is a string comparison, not entailment. Semantic support comes only from
a recorded :class:`SemanticAssessment`, and a claim without one stays visibly unreviewed no
matter how clean its citations are.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from episalpha.contracts.errors import ErrorCode
from episalpha.contracts.knowledge import (
    ALLOWED_ENDPOINTS,
    Claim,
    Entity,
    EpistemicStatus,
    Event,
    EvidenceDocument,
    EvidenceSpan,
    Hypothesis,
    Instrument,
    RecordKind,
    Relation,
    RelationPredicate,
    SemanticAssessment,
    SemanticReviewStatus,
)
from episalpha.contracts.research import CheckResult, RunState, Thesis, ValidationReport
from episalpha.research.derivations import DerivationError, matches, recompute

QUOTATION_CHECK = "exact_quotation_matches_stored_text"
"""Named so no reader mistakes a string match for a judgment about meaning."""


@dataclass(frozen=True)
class RecordSet:
    """Everything the validator is allowed to resolve against.

    ``document_texts`` maps a document id to its normalized text. A document without text can
    have its spans' offsets checked for internal consistency but not their quotations, and the
    validator says so rather than passing silently.
    """

    entities: Sequence[Entity] = ()
    instruments: Sequence[Instrument] = ()
    documents: Sequence[EvidenceDocument] = ()
    spans: Sequence[EvidenceSpan] = ()
    claims: Sequence[Claim] = ()
    events: Sequence[Event] = ()
    hypotheses: Sequence[Hypothesis] = ()
    relations: Sequence[Relation] = ()
    assessments: Sequence[SemanticAssessment] = ()
    theses: Sequence[Thesis] = ()
    document_texts: dict[str, str] = field(default_factory=dict)

    def kinds(self) -> dict[str, RecordKind]:
        """Map every known identifier to its record kind, for endpoint checking."""
        index: dict[str, RecordKind] = {}
        index.update({e.entity_id: RecordKind.ENTITY for e in self.entities})
        index.update({i.instrument_id: RecordKind.INSTRUMENT for i in self.instruments})
        index.update({d.document_id: RecordKind.EVIDENCE_DOCUMENT for d in self.documents})
        index.update({s.span_id: RecordKind.EVIDENCE_SPAN for s in self.spans})
        index.update({c.claim_id: RecordKind.CLAIM for c in self.claims})
        index.update({e.event_id: RecordKind.EVENT for e in self.events})
        index.update({h.hypothesis_id: RecordKind.HYPOTHESIS for h in self.hypotheses})
        index.update({t.thesis_id: RecordKind.THESIS for t in self.theses})
        return index


def _ok(check: str) -> CheckResult:
    return CheckResult(check=check, passed=True)


def _fail(check: str, detail: str) -> CheckResult:
    return CheckResult(check=check, passed=False, detail=detail)


def check_relations(records: RecordSet) -> list[CheckResult]:
    """Endpoints must resolve, and their kinds must be allowed for the predicate."""
    kinds = records.kinds()
    results: list[CheckResult] = []
    for relation in records.relations:
        check = f"relation.{relation.relation_id}"
        source_kind = kinds.get(relation.source_id)
        target_kind = kinds.get(relation.target_id)
        if source_kind is None or target_kind is None:
            missing = relation.source_id if source_kind is None else relation.target_id
            results.append(_fail(check, f"endpoint {missing!r} does not resolve"))
            continue
        allowed_sources, allowed_targets = ALLOWED_ENDPOINTS[relation.predicate]
        if source_kind not in allowed_sources or target_kind not in allowed_targets:
            results.append(
                _fail(
                    check,
                    f"{relation.predicate.value} does not allow "
                    f"{source_kind.value} -> {target_kind.value}",
                )
            )
            continue
        if relation.predicate is RelationPredicate.REPORTS:
            claim = next((c for c in records.claims if c.claim_id == relation.target_id), None)
            if claim is not None and claim.epistemic_status is EpistemicStatus.HYPOTHESIZED:
                results.append(
                    _fail(
                        check,
                        "a span cannot REPORT a hypothesised claim; a mechanism is not "
                        "something a source stated",
                    )
                )
                continue
        results.append(_ok(check))
    return results


def check_claim_references(records: RecordSet) -> list[CheckResult]:
    """Every cited span and derivation input must exist."""
    span_ids = {span.span_id for span in records.spans}
    claim_ids = {claim.claim_id for claim in records.claims}
    results: list[CheckResult] = []
    for claim in records.claims:
        check = f"claim.{claim.claim_id}.references"
        missing_spans = sorted(set(claim.span_ids) - span_ids)
        if missing_spans:
            results.append(_fail(check, f"cites unknown spans {missing_spans}"))
            continue
        if claim.derivation is not None:
            missing_inputs = sorted(set(claim.derivation.input_claim_ids) - claim_ids)
            if missing_inputs:
                results.append(_fail(check, f"derives from unknown claims {missing_inputs}"))
                continue
            if claim.claim_id in claim.derivation.input_claim_ids:
                results.append(_fail(check, "a claim cannot derive from itself"))
                continue
        results.append(_ok(check))
    return results


def check_derivations(records: RecordSet) -> list[CheckResult]:
    """Every derived number must be reproduced by its registered method (amendment A8).

    Claims whose references already failed are skipped, so a missing or circular input is
    reported once, by :func:`check_claim_references`.
    """
    broken = {
        result.check.removeprefix("claim.").removesuffix(".references")
        for result in check_claim_references(records)
        if not result.passed
    }
    claims = {claim.claim_id: claim for claim in records.claims}
    results: list[CheckResult] = []
    for claim in records.claims:
        if claim.derivation is None or claim.claim_id in broken:
            continue
        check = f"claim.{claim.claim_id}.derivation"
        if claim.numeric_fact is None:
            results.append(_fail(check, "derived numeric method requires numeric_fact"))
            continue
        inputs = [claims[claim_id] for claim_id in claim.derivation.input_claim_ids]
        missing = [item.claim_id for item in inputs if item.numeric_fact is None]
        if missing:
            results.append(_fail(check, f"input claim {missing[0]!r} has no numeric_fact"))
            continue
        facts = [item.numeric_fact for item in inputs if item.numeric_fact is not None]
        try:
            value, unit = recompute(claim.derivation, facts)
        except DerivationError as error:
            results.append(_fail(check, str(error)))
            continue
        method = f"{claim.derivation.method}@{claim.derivation.method_version}"
        claimed = claim.numeric_fact
        if claimed.unit != unit:
            results.append(
                _fail(check, f"claims unit {claimed.unit!r} but method {method} produces {unit!r}")
            )
            continue
        if not matches(claimed.value, value):
            results.append(
                _fail(check, f"claims {claimed.value} but {method} recomputed {value} {unit}")
            )
            continue
        results.append(_ok(check))
    return results


def check_quotations(records: RecordSet) -> list[CheckResult]:
    """The quoted passage must match the stored text exactly, at the recorded offsets.

    This is a character comparison. It proves the citation is real; it proves nothing about
    whether the claim follows from it.
    """
    documents = {document.document_id: document for document in records.documents}
    results: list[CheckResult] = []
    for span in records.spans:
        check = f"span.{span.span_id}.{QUOTATION_CHECK}"
        if span.document_id not in documents:
            results.append(_fail(check, f"unknown document {span.document_id!r}"))
            continue
        text = records.document_texts.get(span.document_id)
        if text is None:
            results.append(
                _fail(check, f"no stored text for {span.document_id!r}; quotation unverifiable")
            )
            continue
        if span.end_offset > len(text):
            results.append(_fail(check, f"offsets exceed the document's {len(text)} characters"))
            continue
        actual = text[span.start_offset : span.end_offset]
        if actual != span.exact_quote:
            results.append(_fail(check, f"stored text reads {actual!r}, not {span.exact_quote!r}"))
            continue
        results.append(_ok(check))
    return results


def check_semantic_status(records: RecordSet) -> tuple[list[CheckResult], list[str]]:
    """A non-default review status must be backed by a recorded assessment.

    Returns the checks and the ids of claims still awaiting review, which the report surfaces
    so unreviewed material stays visibly unreviewed.
    """
    latest: dict[str, SemanticAssessment] = {}
    superseded = {
        a.supersedes_assessment_id
        for a in records.assessments
        if a.supersedes_assessment_id is not None
    }
    for assessment in records.assessments:
        if assessment.assessment_id in superseded:
            continue
        latest[assessment.subject_id] = assessment

    results: list[CheckResult] = []
    unresolved: list[str] = []
    for claim in records.claims:
        check = f"claim.{claim.claim_id}.semantic_status"
        current = latest.get(claim.claim_id)
        if claim.semantic_review_status is SemanticReviewStatus.UNREVIEWED:
            unresolved.append(claim.claim_id)
            results.append(_ok(check))
            continue
        if current is None:
            results.append(
                _fail(
                    check,
                    f"claims {claim.semantic_review_status.value!r} with no recorded "
                    "assessment; a clean citation is not a judgment",
                )
            )
            continue
        if current.judgment is not claim.semantic_review_status:
            results.append(
                _fail(
                    check,
                    f"claims {claim.semantic_review_status.value!r} but the current assessment "
                    f"says {current.judgment.value!r}",
                )
            )
            continue
        results.append(_ok(check))
    return results, unresolved


def check_thesis_coverage(thesis: Thesis | None, records: RecordSet) -> list[CheckResult]:
    """Every assertion must resolve to a claim or hypothesis that actually exists."""
    if thesis is None:
        return []
    claim_ids = {claim.claim_id for claim in records.claims}
    hypothesis_ids = {hypothesis.hypothesis_id for hypothesis in records.hypotheses}
    results: list[CheckResult] = []
    for assertion in thesis.assertions:
        check = f"assertion.{assertion.assertion_id}.coverage"
        missing = sorted(
            (set(assertion.claim_ids) - claim_ids)
            | (set(assertion.hypothesis_ids) - hypothesis_ids)
        )
        if missing:
            results.append(_fail(check, f"references unknown records {missing}"))
            continue
        results.append(_ok(check))
    return results


def check_hypotheses(records: RecordSet) -> list[CheckResult]:
    """Supporting and opposing claims must exist; an unsupported mechanism stays a hypothesis."""
    claim_ids = {claim.claim_id for claim in records.claims}
    results: list[CheckResult] = []
    for hypothesis in records.hypotheses:
        check = f"hypothesis.{hypothesis.hypothesis_id}.references"
        referenced = set(hypothesis.supporting_claim_ids) | set(hypothesis.opposing_claim_ids)
        missing = sorted(referenced - claim_ids)
        if missing:
            results.append(_fail(check, f"references unknown claims {missing}"))
            continue
        results.append(_ok(check))
    return results


def validate(
    records: RecordSet,
    run_id: str,
    thesis: Thesis | None = None,
    partial: bool = False,
) -> ValidationReport:
    """Run every deterministic check and produce a terminal disposition.

    ``partial`` marks a run that did real work but did not finish; it produces ``PARTIAL``
    rather than a completion, so an incomplete result is never shown as a whole one.
    """
    semantic_checks, unresolved = check_semantic_status(records)
    checks: list[CheckResult] = [
        *check_relations(records),
        *check_claim_references(records),
        *check_derivations(records),
        *check_quotations(records),
        *semantic_checks,
        *check_hypotheses(records),
        *check_thesis_coverage(thesis, records),
    ]
    structurally_valid = all(check.passed for check in checks)

    if not structurally_valid:
        disposition = RunState.REJECTED
        error_code: ErrorCode | None = ErrorCode.INVALID_OUTPUT
    elif partial:
        disposition = RunState.PARTIAL
        error_code = None
    else:
        disposition = RunState.RESEARCH_COMPLETED
        error_code = None

    warnings: list[str] = []
    if unresolved:
        warnings.append(
            f"{len(unresolved)} claim(s) have no semantic assessment and remain unreviewed"
        )

    return ValidationReport(
        run_id=run_id,
        structurally_valid=structurally_valid,
        checks=tuple(checks),
        unresolved_semantic_reviews=tuple(unresolved),
        warnings=tuple(warnings),
        disposition=disposition,
        error_code=error_code,
    )


def failed_checks(report: ValidationReport) -> tuple[CheckResult, ...]:
    """The failures, for a repair attempt or an honest error message."""
    return tuple(check for check in report.checks if not check.passed)
