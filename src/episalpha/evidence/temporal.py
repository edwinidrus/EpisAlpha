"""Temporal eligibility (plan section 3.5). Pure functions, no I/O.

Six clocks are kept apart here and never collapsed: economic event time, source publication
time, when that exact version became publicly available, when EpisAlpha actually captured it,
the research cutoff, and the run's real execution time.

The rule that does the most work: **a publication date alone never proves that the version we
fetched today existed at that historical date.** Only verified availability does. Everything
else falls back to our own capture time, which is conservative by construction.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from episalpha.contracts.knowledge import AvailabilityBasis, EvidenceDocument
from episalpha.contracts.research import ResearchMode

_VERIFIED = frozenset({AvailabilityBasis.PROVIDER_VERIFIED, AvailabilityBasis.ARCHIVE_VERIFIED})


def eligibility_time(document: EvidenceDocument) -> datetime | None:
    """When this exact version can first be *proven* to have been available.

    Returns ``None`` when availability is unresolved, which disqualifies the document from any
    earlier cutoff rather than guessing in its favour (rule 4).
    """
    if document.availability_basis in _VERIFIED:
        return document.public_available_at
    if document.availability_basis is AvailabilityBasis.FIRST_CAPTURE:
        # Rule 2: our own capture is the conservative eligibility time.
        return document.ingested_at
    return None


def is_eligible(document: EvidenceDocument, cutoff: datetime, mode: ResearchMode) -> bool:
    """Is this document version usable for a run with this cutoff?

    Boundary: a version available *exactly at* the cutoff is eligible.
    """
    if mode is ResearchMode.HISTORICAL_RECONSTRUCTION:
        # Rule 1, 3 and 4: only a provable availability time reaches back in time. A document
        # first captured today cannot be shown to have existed at a past cutoff, whatever its
        # printed publication date says.
        available_at = eligibility_time(document)
        return available_at is not None and available_at <= cutoff

    # Rule 5: a forward run must actually have held the document before the snapshot froze.
    if document.ingested_at > cutoff:
        return False
    available_at = eligibility_time(document)
    return available_at is None or available_at <= cutoff


def eligible_documents(
    documents: Iterable[EvidenceDocument], cutoff: datetime, mode: ResearchMode
) -> tuple[EvidenceDocument, ...]:
    """Every version that qualifies, in no particular order."""
    return tuple(d for d in documents if is_eligible(d, cutoff, mode))


def select_current_versions(
    documents: Iterable[EvidenceDocument], cutoff: datetime, mode: ResearchMode
) -> tuple[EvidenceDocument, ...]:
    """The latest qualifying version of each source family, as of the cutoff.

    Rule 6: not today's latest version, and not invariably the first-reported one. A correction
    published after the cutoff must not overwrite what was knowable at the cutoff, and older
    versions are retained rather than discarded.
    """
    latest: dict[str, EvidenceDocument] = {}
    for document in eligible_documents(documents, cutoff, mode):
        available_at = eligibility_time(document)
        if available_at is None:  # pragma: no cover - eligibility already guarantees a time
            continue
        incumbent = latest.get(document.source_family_id)
        if incumbent is None:
            latest[document.source_family_id] = document
            continue
        incumbent_at = eligibility_time(incumbent)
        assert incumbent_at is not None
        # Ties break on document_id so the selection is deterministic across runs.
        if (available_at, document.document_id) > (incumbent_at, incumbent.document_id):
            latest[document.source_family_id] = document
    return tuple(latest[key] for key in sorted(latest))


def is_prior_record_available(created_at: datetime, cutoff: datetime) -> bool:
    """May an earlier run's output be shown to a run with this cutoff?

    Rule 9: prior theses, semantic assessments and outcome lessons are hindsight unless they
    actually existed by the cutoff. Rule 8 is the other half of this — a claim written today
    from old evidence keeps today's ``created_at``, so it correctly fails this check for a past
    cutoff. Evidence cutoff and creation time are separate clocks; neither is backdated.
    """
    return created_at <= cutoff
