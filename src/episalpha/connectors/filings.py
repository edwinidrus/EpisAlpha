"""SEC EDGAR filings connector (plan M2-T03).

Three EDGAR clocks are kept apart, because collapsing them is how lookahead bias gets in:

* ``filing_date`` — the date the filer says the document belongs to.
* ``acceptance_datetime`` — when EDGAR accepted the submission.
* **verified availability** — when that exact document was publicly retrievable.

Acceptance is the moment EDGAR disseminates, so it is the defensible availability time and maps
to ``provider_verified``. A filing date alone never is: it is an assertion on the document, not
evidence that the bytes we hold today existed then. When acceptance is missing we fall back to
our own capture time with ``first_capture``, which is conservative by construction.

The connector takes a transport callable so the default suite ingests recorded fixtures with no
network. It records what a source said; it never infers an investment conclusion.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from pydantic import Field

from episalpha.connectors.prices import SourceError, Transport, fetch_span, record_payload
from episalpha.contracts.errors import ErrorCode
from episalpha.contracts.knowledge import (
    AvailabilityBasis,
    Contract,
    EvidenceDocument,
    UtcTimestamp,
)
from episalpha.evidence.parsing import PARSER_VERSION, extract_text, parsed_text_hash
from episalpha.storage.objects import ObjectStore

ALLOWED_HOSTS = frozenset({"www.sec.gov", "sec.gov", "data.sec.gov"})
"""Fetching is allowlisted. A connector that will follow any URL is a fetch-anything gadget."""


def user_agent(application: str, contact: str) -> str:
    """EDGAR fair access requires a descriptive agent carrying real contact details."""
    if "@" not in contact:
        raise ValueError(
            "SEC fair access requires contact details a human can reach, such as an email address"
        )
    return f"{application} ({contact})"


def check_allowed(url: str) -> None:
    host = urlparse(url).netloc.lower()
    if host not in ALLOWED_HOSTS:
        raise SourceError(
            ErrorCode.NOT_AUTHORIZED,
            f"{host!r} is not an allowlisted SEC host; allowed: {sorted(ALLOWED_HOSTS)}",
        )


class FilingMetadata(Contract):
    """One filing as EDGAR describes it, before it becomes evidence."""

    accession_number: str = Field(min_length=1)
    cik: str = Field(pattern=r"^\d{10}$")
    form_type: str = Field(min_length=1)
    filing_date: UtcTimestamp
    acceptance_datetime: UtcTimestamp | None = None
    primary_document: str = Field(min_length=1)
    source_uri: str = Field(min_length=1)

    @property
    def source_family_id(self) -> str:
        """Every version of one filing shares this lineage, so revisions stay connected.

        Two outlets republishing the same filing are not independent confirmation; a shared
        family id is what makes that visible rather than double-counted.
        """
        return f"sec-{self.cik}-{self.accession_number.replace('-', '')}".lower()


class SecEdgarFilings:
    """Ingests preserved SEC payloads and, when permitted, fetches them."""

    source_id = "sec_edgar"

    def __init__(
        self,
        object_store: ObjectStore,
        *,
        transport: Transport | None = None,
        agent: str | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.object_store = object_store
        self.transport = transport
        self.agent = agent
        self._now = now

    def ingest(
        self,
        metadata: FilingMetadata,
        payload: bytes,
        *,
        document_id: str,
        revises_document_id: str | None = None,
    ) -> tuple[EvidenceDocument, str]:
        """Preserve one filing and derive its document record and normalized text.

        The original bytes go to the content-addressed store first, so the record always points
        at something retrievable.
        """
        payload_hash = self.object_store.put(payload)
        text = extract_text(payload)
        ingested_at = self._now()

        if metadata.acceptance_datetime is not None:
            available_at: datetime | None = metadata.acceptance_datetime
            basis = AvailabilityBasis.PROVIDER_VERIFIED
        else:
            # No acceptance time means no proof of when this version was retrievable. Our own
            # capture is the conservative answer; the filing date is not evidence.
            available_at = ingested_at
            basis = AvailabilityBasis.FIRST_CAPTURE

        document = EvidenceDocument(
            document_id=document_id,
            source_uri=metadata.source_uri,
            source_type=f"sec_{metadata.form_type.lower().replace('-', '_')}",
            source_family_id=metadata.source_family_id,
            payload_hash=payload_hash,
            parsed_text_hash=parsed_text_hash(text),
            parser_version=PARSER_VERSION,
            published_at=metadata.filing_date,
            public_available_at=available_at,
            availability_basis=basis,
            ingested_at=ingested_at,
            revises_document_id=revises_document_id,
        )
        return document, text

    def fetch(self, url: str) -> bytes:
        """Fetch one allowlisted SEC URL. Requires an explicitly configured transport."""
        with fetch_span(self.source_id, "fetch", urlparse(url).hostname) as current:
            check_allowed(url)
            if self.transport is None or self.agent is None:
                raise SourceError(
                    ErrorCode.NOT_AUTHORIZED,
                    "network fetching is not configured; supply a transport and a User-Agent "
                    "carrying contact details, per SEC fair access",
                )
            try:
                body = self.transport({"url": url, "User-Agent": self.agent})
            except SourceError:
                raise
            except Exception as error:
                raise SourceError(
                    ErrorCode.SOURCE_FAILED, f"{self.source_id} transport failed: {error}"
                ) from error
            payload = body.encode("utf-8") if isinstance(body, str) else body
            record_payload(current, payload)
            return payload

    def parse_submissions(self, body: str, *, forms: tuple[str, ...] = ()) -> list[FilingMetadata]:
        """Read EDGAR's submissions JSON into filing metadata.

        An empty recent-filings list is ``NO_DATA``: EDGAR answered and had nothing. A malformed
        or truncated response is ``SOURCE_FAILED``, because we did not actually get to look.
        """
        try:
            document: dict[str, Any] = json.loads(body)
        except json.JSONDecodeError as error:
            raise SourceError(
                ErrorCode.SOURCE_FAILED, f"{self.source_id} returned unparseable content"
            ) from error

        cik_value = document.get("cik")
        recent = document.get("filings", {}).get("recent")
        if cik_value is None or not isinstance(recent, dict):
            raise SourceError(
                ErrorCode.SOURCE_FAILED,
                f"{self.source_id} response is missing the expected submissions structure",
            )

        cik = f"{int(cik_value):010d}"
        accessions = recent.get("accessionNumber", [])
        if not accessions:
            raise SourceError(ErrorCode.NO_DATA, f"{self.source_id} lists no filings for {cik}")

        filings: list[FilingMetadata] = []
        for index, accession in enumerate(accessions):
            form = recent["form"][index]
            if forms and form not in forms:
                continue
            acceptance = recent.get("acceptanceDateTime", [None] * len(accessions))[index]
            primary = recent["primaryDocument"][index]
            plain = accession.replace("-", "")
            filings.append(
                FilingMetadata(
                    accession_number=accession,
                    cik=cik,
                    form_type=form,
                    filing_date=_as_utc(recent["filingDate"][index]),
                    acceptance_datetime=_as_utc(acceptance) if acceptance else None,
                    primary_document=primary,
                    source_uri=(
                        f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{plain}/{primary}"
                    ),
                )
            )
        if not filings:
            raise SourceError(
                ErrorCode.NO_DATA,
                f"{self.source_id} has no {'/'.join(forms)} filings for {cik}",
            )
        return filings


def _as_utc(value: str) -> datetime:
    """EDGAR dates are naive US/Eastern-ish strings; anchor them explicitly rather than guess."""
    text = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text) if "T" in text else datetime.fromisoformat(f"{text}")
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
