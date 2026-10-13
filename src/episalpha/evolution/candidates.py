"""The candidate surface: one allowed mutation, validated as data (plan section 12.2, M6-T02).

A proposal is JSON from a candidate author. The only patch that passes is exactly one
``replace`` of ``/contradiction_search`` with a boolean the parent does not already have
(M6 article 3). Nothing a proposal contains is executed or imported (article 4); this is
deliberately not a JSON-Patch engine.

An accepted candidate is materialized as a *copy* of the baseline harness under the candidates
directory, with the patched ``config.json``; the baseline is never written. Every proposal,
accepted or rejected, every materialization and every abandonment goes into an append-only
JSON-lines ledger (article 7).
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import Field, JsonValue, ValidationError

from episalpha.contracts.errors import EpisAlphaError, ErrorCode
from episalpha.contracts.knowledge import Contract
from episalpha.observability import SpanKind, span
from episalpha.runtime.hermes import Harness, load_harness

FLAG = "contradiction_search"
ALLOWED_PATH = f"/{FLAG}"


class CandidateRejected(EpisAlphaError):
    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.INVALID_OUTPUT, message)


class PatchOperation(Contract):
    op: str
    path: str
    value: JsonValue = None


class CandidateProposal(Contract):
    parent_harness_id: str = Field(min_length=1)
    hypothesis: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    patch: tuple[PatchOperation, ...]


@dataclass(frozen=True)
class ValidatedCandidate:
    candidate_id: str
    proposal: CandidateProposal
    parent_harness_id: str
    parent_harness_hash: str
    config: Mapping[str, Any]


def validate_proposal(raw: Mapping[str, Any], parent: Harness) -> ValidatedCandidate:
    """Accept exactly the one permitted flag change against ``parent``, or raise."""
    try:
        proposal = CandidateProposal.model_validate(raw)
    except ValidationError as error:
        first = error.errors()[0]
        where = ".".join(str(part) for part in first["loc"])
        raise CandidateRejected(f"malformed proposal: {where}: {first['msg']}") from None
    if proposal.parent_harness_id != parent.harness_id:
        raise CandidateRejected(
            f"parent {proposal.parent_harness_id!r} is not the baseline {parent.harness_id!r}"
        )
    if len(proposal.patch) != 1:
        raise CandidateRejected(
            f"the patch must hold exactly one operation, not {len(proposal.patch)}"
        )
    (operation,) = proposal.patch
    if operation.op != "replace":
        raise CandidateRejected(f"only 'replace' is allowed, not {operation.op!r}")
    if operation.path != ALLOWED_PATH:
        raise CandidateRejected(f"only {ALLOWED_PATH} may change, not {operation.path!r}")
    if not isinstance(operation.value, bool):
        raise CandidateRejected(f"{ALLOWED_PATH} takes a boolean, not {operation.value!r}")
    if parent.config.get(FLAG) == operation.value:
        raise CandidateRejected(f"{ALLOWED_PATH} is already {operation.value} in the parent")
    identity = json.dumps(
        [parent.harness_hash, proposal.model_dump(mode="json")], sort_keys=True
    ).encode()
    return ValidatedCandidate(
        candidate_id=f"cand-{hashlib.sha256(identity).hexdigest()[:16]}",
        proposal=proposal,
        parent_harness_id=parent.harness_id,
        parent_harness_hash=parent.harness_hash,
        config={**parent.config, FLAG: operation.value},
    )


class Ledger:
    """Append-only JSON lines. Records are added, never rewritten or removed."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, kind: str, *, campaign_id: str, now: datetime, **fields: Any) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        record = {"at": now.isoformat(), "campaign_id": campaign_id, "kind": kind, **fields}
        with self.path.open("a") as handle:
            handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")

    def records(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]


def propose(
    raw: Mapping[str, Any],
    baseline_root: Path,
    ledger: Ledger,
    *,
    campaign_id: str,
    now: datetime,
) -> ValidatedCandidate:
    """Validate a proposal against the baseline and record the outcome either way."""
    with span("candidate.review", SpanKind.EVALUATOR, **{"episalpha.campaign_id": campaign_id}):
        parent = load_harness(baseline_root)
        try:
            candidate = validate_proposal(raw, parent)
        except CandidateRejected as rejected:
            ledger.append(
                "proposal_rejected",
                campaign_id=campaign_id,
                now=now,
                reason=str(rejected),
                parent_harness_hash=parent.harness_hash,
                proposal=dict(raw),
            )
            raise
        ledger.append(
            "proposal_accepted",
            campaign_id=campaign_id,
            now=now,
            candidate_id=candidate.candidate_id,
            parent_harness_id=candidate.parent_harness_id,
            parent_harness_hash=candidate.parent_harness_hash,
            proposal=candidate.proposal.model_dump(mode="json"),
        )
    return candidate


@dataclass(frozen=True)
class Materialized:
    candidate_id: str
    root: Path
    harness_id: str
    parent_hash: str
    child_hash: str


def materialize(
    candidate: ValidatedCandidate,
    baseline_root: Path,
    candidates_root: Path,
    ledger: Ledger,
    *,
    now: datetime,
    campaign_id: str = "",
) -> Materialized:
    """Copy the baseline to ``<candidates_root>/<candidate_id>/`` and apply the patch there."""
    target = candidates_root / candidate.candidate_id
    if target.resolve().is_relative_to(baseline_root.resolve()):
        raise EpisAlphaError(
            ErrorCode.NOT_AUTHORIZED, "a candidate is never written inside the baseline harness"
        )
    parent = load_harness(baseline_root)
    if parent.harness_hash != candidate.parent_harness_hash:
        raise EpisAlphaError(
            ErrorCode.INTEGRITY_ERROR, "the baseline changed since this candidate was validated"
        )
    config = json.dumps(candidate.config, indent=2) + "\n"
    if not target.exists():
        staging = candidates_root / f".{candidate.candidate_id}.tmp"
        shutil.rmtree(staging, ignore_errors=True)
        shutil.copytree(baseline_root, staging)
        (staging / "config.json").write_text(config)
        staging.rename(target)
    child = load_harness(target)
    pristine = {
        path.relative_to(baseline_root).as_posix(): path.read_bytes()
        for path in baseline_root.rglob("*")
        if path.is_file() and path.name != "config.json"
    }
    present = {
        path.relative_to(target).as_posix(): path.read_bytes()
        for path in target.rglob("*")
        if path.is_file() and path.name != "config.json"
    }
    if dict(child.config) != json.loads(config) or present != pristine:
        raise EpisAlphaError(
            ErrorCode.INTEGRITY_ERROR,
            f"candidate directory {target.name} differs from baseline plus patch; not reused",
        )
    made = Materialized(
        candidate_id=candidate.candidate_id,
        root=target,
        harness_id=child.harness_id,
        parent_hash=parent.harness_hash,
        child_hash=child.harness_hash,
    )
    if not any(
        r["kind"] == "materialized" and r.get("candidate_id") == made.candidate_id
        for r in ledger.records()
    ):
        ledger.append(
            "materialized",
            campaign_id=campaign_id,
            now=now,
            candidate_id=made.candidate_id,
            parent_harness_hash=made.parent_hash,
            child_harness_hash=made.child_hash,
        )
    return made


def abandon(
    ledger: Ledger, candidate_id: str, reason: str, campaign_id: str, *, now: datetime
) -> None:
    """Record that a candidate was dropped. It stays in the ledger; nothing is deleted."""
    ledger.append(
        "abandoned", campaign_id=campaign_id, now=now, candidate_id=candidate_id, reason=reason
    )
