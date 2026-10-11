"""What each research stage may submit (plan section 3.6, stages 3-6; amendment A3).

A stage ends by calling its ``submit_<stage>`` tool. The arguments are a *candidate*: the host
parses them here after the stage, and only then validates references, recomputes numbers and
assigns canonical IDs (``<run_id>.<key>``). Nothing a model submits is canonical by itself.

The schemas are strict (unknown fields are rejected) and numbers are decimal strings, never
JSON floats. The JSON schemas handed to the model are inlined, without ``$ref``, because some
providers mishandle references in tool parameters.
"""

from __future__ import annotations

from typing import Annotated, Any, Self

from pydantic import Field, StringConstraints, model_validator

from episalpha.contracts.knowledge import (
    Contract,
    DecimalString,
    EpistemicStatus,
    UtcTimestamp,
)
from episalpha.contracts.research import ResearchStance, RunState, ThesisSection

CandidateKey = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_-]{0,15}$")]
"""A model-chosen local key; the host turns it into the canonical ``<run_id>.<key>``."""
RecordRef = Annotated[str, StringConstraints(min_length=3, max_length=96)]
"""A snapshot ID or a validated current-run ID. Existence is checked by the host validator."""
Text = Annotated[str, StringConstraints(min_length=1, max_length=2000)]


class CandidateNumericFact(Contract):
    metric: Text
    value: DecimalString
    unit: Text
    period_start: UtcTimestamp
    period_end: UtcTimestamp
    accounting_basis: Text
    source_context: Text


class CandidateDerivation(Contract):
    method: Text
    method_version: Text
    input_claim_ids: tuple[RecordRef, ...] = Field(min_length=1)


class CandidateClaim(Contract):
    key: CandidateKey
    statement: Text
    attribution: Text
    epistemic_status: EpistemicStatus
    span_ids: tuple[RecordRef, ...] = ()
    derivation: CandidateDerivation | None = None
    numeric_fact: CandidateNumericFact | None = None

    @model_validator(mode="after")
    def _reported_or_derived(self) -> Self:
        if self.epistemic_status is EpistemicStatus.HYPOTHESIZED:
            raise ValueError("a mechanism is submitted as a hypothesis, not as a claim")
        if self.epistemic_status is EpistemicStatus.REPORTED and not self.span_ids:
            raise ValueError(f"reported claim {self.key!r} must cite at least one span ID")
        if self.epistemic_status is EpistemicStatus.DERIVED and self.derivation is None:
            raise ValueError(f"derived claim {self.key!r} must name its derivation")
        return self


class CandidateHypothesis(Contract):
    key: CandidateKey
    mechanism: Text
    assumptions: tuple[Text, ...] = Field(min_length=1)
    supporting_claim_ids: tuple[RecordRef, ...] = ()
    opposing_claim_ids: tuple[RecordRef, ...] = ()
    falsification_condition: Text
    horizon_trading_days: int = Field(gt=0, le=1000)


def _unique_keys(items: tuple[CandidateClaim, ...] | tuple[CandidateHypothesis, ...]) -> None:
    keys = [item.key for item in items]
    if len(set(keys)) != len(keys):
        raise ValueError(f"keys must be unique within a submission: {keys}")


class ResearchCandidate(Contract):
    """Researcher output: claims citing snapshot spans, and candidate hypotheses."""

    claims: tuple[CandidateClaim, ...] = Field(max_length=40)
    hypotheses: tuple[CandidateHypothesis, ...] = Field(default=(), max_length=10)

    @model_validator(mode="after")
    def _keys(self) -> Self:
        _unique_keys(self.claims)
        _unique_keys(self.hypotheses)
        if {c.key for c in self.claims} & {h.key for h in self.hypotheses}:
            raise ValueError("a claim and a hypothesis cannot share a key")
        return self


class Contradiction(Contract):
    claim_id: RecordRef
    contradicted_by_claim_id: RecordRef
    span_ids: tuple[RecordRef, ...] = ()


class CritiqueCandidate(Contract):
    """Critic output: contradictions found, new counter-evidence claims, explicit unknowns."""

    contradictions: tuple[Contradiction, ...] = Field(default=(), max_length=20)
    counter_claims: tuple[CandidateClaim, ...] = Field(default=(), max_length=20)
    missing_information: tuple[Text, ...] = Field(default=(), max_length=20)

    @model_validator(mode="after")
    def _keys(self) -> Self:
        _unique_keys(self.counter_claims)
        return self


class CandidateAssertion(Contract):
    section: ThesisSection
    text: Text
    claim_ids: tuple[RecordRef, ...] = ()
    hypothesis_ids: tuple[RecordRef, ...] = ()

    @model_validator(mode="after")
    def _references_something(self) -> Self:
        if not self.claim_ids and not self.hypothesis_ids:
            raise ValueError("every assertion must reference a claim or a hypothesis")
        return self


class ThesisCandidate(Contract):
    """Synthesizer output; the host builds the canonical :class:`Thesis` from it."""

    stance: ResearchStance
    assertions: tuple[CandidateAssertion, ...] = Field(min_length=1, max_length=20)
    missing_information: tuple[Text, ...] = Field(default=(), max_length=20)
    next_inquiry: Text


CANDIDATES: dict[RunState, type[Contract]] = {
    RunState.RESEARCHING: ResearchCandidate,
    RunState.CRITIQUING: CritiqueCandidate,
    RunState.SYNTHESIZING: ThesisCandidate,
}
SUBMIT_TOOLS: dict[RunState, str] = {
    RunState.RESEARCHING: "submit_research",
    RunState.CRITIQUING: "submit_critique",
    RunState.SYNTHESIZING: "submit_thesis",
}
PROVENANCE_KEYS = frozenset({"fixture", "source"})
"""Labels a fake runtime adds to its payloads; stripped before parsing."""


def parse_candidate(stage: RunState, payload: dict[str, Any]) -> Contract:
    """Parse one stage's submission. Raises ``pydantic.ValidationError`` when malformed."""
    cleaned = {key: value for key, value in payload.items() if key not in PROVENANCE_KEYS}
    return CANDIDATES[stage].model_validate(cleaned)


def _inline(node: Any, definitions: dict[str, Any]) -> Any:
    if isinstance(node, dict):
        reference = node.get("$ref")
        if isinstance(reference, str):
            return _inline(definitions[reference.rsplit("/", 1)[-1]], definitions)
        return {
            key: _inline(value, definitions)
            for key, value in node.items()
            if key not in ("$defs", "title")
        }
    if isinstance(node, list):
        return [_inline(item, definitions) for item in node]
    return node


def _decimal_strings(node: Any) -> Any:
    """Pydantic renders ``Decimal`` as number-or-string; the model must send a string."""
    if isinstance(node, dict):
        if (
            "anyOf" in node
            and {"type": "string"}
            in [{k: v for k, v in option.items() if k == "type"} for option in node["anyOf"]]
            and any(option.get("type") == "number" for option in node["anyOf"])
        ):
            return {"type": "string", "description": "a decimal number written as a string"}
        return {key: _decimal_strings(value) for key, value in node.items()}
    if isinstance(node, list):
        return [_decimal_strings(item) for item in node]
    return node


def submit_schema(stage: RunState) -> dict[str, Any]:
    """The inlined JSON schema for the stage's ``submit_<stage>`` tool parameters."""
    schema = CANDIDATES[stage].model_json_schema()
    inlined = _inline(schema, schema.get("$defs", {}))
    return dict(_decimal_strings(inlined))
