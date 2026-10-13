"""Evaluation cases and sealed labels (plan section 12.1, M6-T01).

A case is what a research run receives: an instrument, a question, a cutoff and the evidence it
may read. Its labels are what the evaluator alone knows: the fact and contradiction IDs a good
answer recovers, the passages that support it, and whether the honest answer is to abstain.

Labels are sealed (M6 article 2). They live in ``evaluation.labels_dir`` from settings, which
must sit outside both ``project_root`` and ``data_root``, so neither the research worker (it sees
a snapshot and a stage directory under ``data_root``) nor a candidate author (it sees the
repository) can reach them. :func:`load_labels` re-checks that on every load.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable
from enum import StrEnum
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, ValidationError, model_validator

from episalpha.contracts.errors import EpisAlphaError, ErrorCode
from episalpha.contracts.knowledge import Contract, DecimalString, Identifier, UtcTimestamp
from episalpha.contracts.research import ResearchMode
from episalpha.settings import Settings

EVALUATOR = "evaluator"
EVALUATOR_SOURCES = (Path(__file__), Path(__file__).with_name("scoring.py"))
"""The code whose behaviour the evaluator hash pins, alongside the label files."""


class Partition(StrEnum):
    DEVELOPMENT = "development"
    """Labels visible for failure analysis."""
    VALIDATION = "validation"
    """Labels for the evaluator only."""
    FINAL = "final"
    """Inputs and labels withheld until the configuration is frozen."""


class CaseType(StrEnum):
    """The case types plan section 12.1 requires."""

    EXTRACTION = "extraction"
    SOURCE_ATTRIBUTION = "source_attribution"
    NUMERIC_UNITS_PERIODS = "numeric_units_periods"
    CONTRADICTION = "contradiction"
    DUPLICATE_LINEAGE = "duplicate_lineage"
    MISSING_EVIDENCE = "missing_evidence"
    FUTURE_EVIDENCE = "future_evidence"
    INJECTED_INSTRUCTION = "injected_instruction"


class EvalCase(Contract):
    """One research task. Carries no label: it is safe to hand to a run."""

    schema_version: Literal["1"] = "1"
    case_id: Identifier
    partition: Partition
    family_id: Identifier
    """Source, document or event family. One family never spans two partitions."""
    case_type: CaseType
    instrument_id: Identifier
    snapshot_ref: str = Field(min_length=1)
    """``synthetic`` (the demo corpus) or the ID of a frozen snapshot."""
    question: str = Field(min_length=1)
    research_cutoff: UtcTimestamp
    research_mode: ResearchMode = ResearchMode.HISTORICAL_RECONSTRUCTION


class ExpectedFact(Contract):
    """A fact a good answer recovers: a factual claim citing one of these passages."""

    fact_id: Identifier
    span_ids: tuple[Identifier, ...] = Field(min_length=1)
    value: DecimalString | None = None
    """When set, the claim's numeric fact must equal it, in ``unit``."""
    unit: str | None = None


class ExpectedContradiction(Contract):
    """Recovered by a ``CONTRADICTS`` relation between claims citing one side each."""

    contradiction_id: Identifier
    side_a_span_ids: tuple[Identifier, ...] = Field(min_length=1)
    side_b_span_ids: tuple[Identifier, ...] = Field(min_length=1)


class Labels(Contract):
    """Human-owned gold for one case. Never a repair target (global article 17)."""

    schema_version: Literal["1"] = "1"
    case_id: Identifier
    facts: tuple[ExpectedFact, ...] = ()
    contradictions: tuple[ExpectedContradiction, ...] = ()
    should_abstain: bool | None = None
    """``None`` when the case requires no abstain decision."""
    supporting_span_ids: tuple[Identifier, ...] = ()
    """Passages a correct citation may point at. Empty means the facts' passages."""
    reviewed_by: str | None = None
    reviewed_at: UtcTimestamp | None = None
    """The owner checkpoint: who validated these labels, and when."""

    @model_validator(mode="after")
    def _ids_unique(self) -> Self:
        for kind, ids in (
            ("fact", [item.fact_id for item in self.facts]),
            ("contradiction", [item.contradiction_id for item in self.contradictions]),
        ):
            if len(set(ids)) != len(ids):
                raise ValueError(f"duplicate {kind} IDs in labels for {self.case_id!r}")
        return self

    @property
    def citable_span_ids(self) -> frozenset[str]:
        if self.supporting_span_ids:
            return frozenset(self.supporting_span_ids)
        return frozenset(span for fact in self.facts for span in fact.span_ids)


def _refuse(message: str, code: ErrorCode = ErrorCode.INVALID_REQUEST) -> EpisAlphaError:
    return EpisAlphaError(code, message)


def _read[C: Contract](model: type[C], path: Path) -> C:
    try:
        return model.model_validate(json.loads(path.read_text()))
    except (ValidationError, json.JSONDecodeError) as error:
        raise _refuse(f"{path.name}: {error}") from None


def load_cases(directory: Path) -> list[EvalCase]:
    """Every ``<case_id>.json`` in ``directory``, in a stable order."""
    cases = []
    for path in sorted(directory.glob("*.json")):
        item = _read(EvalCase, path)
        if path.stem != item.case_id:
            raise _refuse(f"{path.name} holds case {item.case_id!r}; name the file after it")
        cases.append(item)
    return cases


def check_partitions(cases: Iterable[EvalCase]) -> None:
    """Refuse duplicate case IDs and any family that appears in more than one partition."""
    seen: set[str] = set()
    partitions: dict[str, set[Partition]] = defaultdict(set)
    for item in cases:
        if item.case_id in seen:
            raise _refuse(f"case {item.case_id!r} appears twice")
        seen.add(item.case_id)
        partitions[item.family_id].add(item.partition)
    leaking = sorted(family for family, found in partitions.items() if len(found) > 1)
    if leaking:
        raise _refuse(f"families span partitions (near-duplicate evidence leaks): {leaking}")


def _inside(path: Path, root: Path) -> bool:
    return path.resolve().is_relative_to(root.resolve())


def load_labels(settings: Settings, *, caller: str) -> dict[str, Labels]:
    """The sealed labels, by case ID. Only the evaluator may call this."""
    if caller != EVALUATOR:
        raise _refuse(
            f"{caller!r} may not read labels; only the evaluator does (M6 article 2)",
            ErrorCode.NOT_AUTHORIZED,
        )
    directory = settings.evaluation.labels_dir
    if directory is None:
        raise _refuse("evaluation.labels_dir is not configured; labels have no sealed home")
    for name, root in (
        ("project_root", settings.paths.project_root),
        ("data_root", settings.paths.data_root),
    ):
        if _inside(directory, root):
            raise _refuse(
                f"labels_dir {directory} is inside {name}, part of the agent-accessible "
                "workspace; move the labels outside it",
                ErrorCode.NOT_AUTHORIZED,
            )
    labels: dict[str, Labels] = {}
    for path in sorted(directory.glob("*.json")):
        item = _read(Labels, path)
        if path.stem != item.case_id:
            raise _refuse(f"{path.name} holds labels for {item.case_id!r}; name it after the case")
        labels[item.case_id] = item
    return labels


def _digest(paths: Iterable[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.name.encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def labels_hash(directory: Path) -> str:
    """SHA-256 over every label file's name and bytes."""
    return _digest(sorted(directory.glob("*.json")))


def evaluator_hash(directory: Path) -> str:
    """SHA-256 over the scoring code and the label files: the evaluator's frozen identity."""
    return _digest([*EVALUATOR_SOURCES, *sorted(directory.glob("*.json"))])
