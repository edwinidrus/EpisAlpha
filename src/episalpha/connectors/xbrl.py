"""SEC XBRL company facts, selected point in time (plan M2-T05, amendment A8).

``companyfacts`` lists every value a company ever filed for every concept, one entry per filing
(accession). The same period often appears several times: in the original 10-Q, as a comparative
in later filings, and sometimes restated with a different value. Choosing "the" value for a
research cutoff is therefore a temporal decision, made here by one rule:

    A fact is available from its accession's **acceptance datetime** (from the submissions data,
    see :class:`~episalpha.connectors.filings.FilingMetadata`). Among facts for the same concept,
    unit and period, the latest one accepted at or before the cutoff wins. A fact whose
    acceptance time is unknown is not eligible, whatever its ``filed`` date says.

SEC's aggregate-by-period API is deliberately never used: it answers with the last-filed value,
which may be a restatement published after the cutoff.

Field names (``start``, ``end``, ``val``, ``accn``, ``fy``, ``fp``, ``form``, ``filed``,
``frame``) were verified against LULU's real payload on 2026-10-10. Numbers are read as
``Decimal`` at the JSON boundary; no value ever passes through a float.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from pydantic import Field, ValidationError

from episalpha.connectors.filings import check_allowed
from episalpha.connectors.prices import SourceError, Transport, fetch_span, record_payload
from episalpha.contracts.errors import ErrorCode
from episalpha.contracts.knowledge import (
    AvailabilityBasis,
    Contract,
    DecimalString,
    EvidenceDocument,
    EvidenceSpan,
    NumericFact,
)
from episalpha.evidence.parsing import PARSER_VERSION, extract_text, make_span, parsed_text_hash
from episalpha.storage.objects import ObjectStore

COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
_CIK = re.compile(r"^\d{10}$")
# A fact entry is a flat JSON object; concept and unit containers always nest.
_FLAT_OBJECT = re.compile(r"\{[^{}]*\}")

Period = tuple[date | None, date]


class XbrlFact(Contract):
    """One filed value of one concept, exactly as ``companyfacts`` lists it."""

    taxonomy: str = Field(min_length=1)
    concept: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    index: int = Field(ge=0)
    """Position in the payload's ``units[unit]`` array, so the exact text can be located."""
    start: date | None = None
    end: date
    value: DecimalString
    accession: str = Field(min_length=1)
    form: str = Field(min_length=1)
    filed: date
    fy: int | None = None
    fp: str | None = None
    frame: str | None = None
    """Recorded as filed; never used for selection."""

    @property
    def period(self) -> Period:
        return (self.start, self.end)

    @property
    def locator(self) -> str:
        return f"{self.taxonomy}:{self.concept}/{self.unit}[{self.index}]"


def _midnight(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


def _short_hash(*parts: object) -> str:
    return hashlib.sha256("|".join(str(part) for part in parts).encode()).hexdigest()


class SecXbrlFacts:
    """Fetches, preserves and parses ``companyfacts``; selects facts as of a cutoff."""

    source_id = "sec_xbrl"

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

    def fetch_companyfacts(self, cik: str) -> bytes:
        """Fetch one company's facts. Requires an explicit transport and SEC User-Agent."""
        if not _CIK.match(cik):
            raise SourceError(ErrorCode.INVALID_REQUEST, f"{cik!r} is not a 10-digit CIK")
        url = COMPANYFACTS_URL.format(cik=cik)
        with fetch_span(self.source_id, "companyfacts", "data.sec.gov") as current:
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

    def parse(self, body: bytes) -> list[XbrlFact]:
        """Every fact in the payload. Malformed is ``SOURCE_FAILED``; empty is ``NO_DATA``."""
        try:
            document: Any = json.loads(body, parse_float=Decimal, parse_int=Decimal)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise SourceError(
                ErrorCode.SOURCE_FAILED, f"{self.source_id} returned unparseable content"
            ) from error
        facts = document.get("facts") if isinstance(document, dict) else None
        if not isinstance(facts, dict):
            raise SourceError(
                ErrorCode.SOURCE_FAILED, f"{self.source_id} response has no 'facts' object"
            )
        if not facts:
            raise SourceError(ErrorCode.NO_DATA, f"{self.source_id} lists no facts")
        parsed: list[XbrlFact] = []
        try:
            for taxonomy, concepts in facts.items():
                for concept, body_ in concepts.items():
                    for unit, items in body_.get("units", {}).items():
                        for index, item in enumerate(items):
                            parsed.append(_fact(taxonomy, concept, unit, index, item))
        except (AttributeError, KeyError, TypeError, ValidationError) as error:
            raise SourceError(
                ErrorCode.SOURCE_FAILED, f"{self.source_id} fact entry is malformed: {error}"
            ) from error
        return parsed

    @staticmethod
    def select_as_of(
        facts: Sequence[XbrlFact],
        concept: str,
        unit: str,
        period: Period,
        availability: Mapping[str, datetime | None],
        cutoff: datetime,
        *,
        taxonomy: str = "us-gaap",
    ) -> XbrlFact | None:
        """The value publicly available at ``cutoff``, or ``None`` when none qualifies.

        ``availability`` maps accession number to acceptance datetime. An unknown concept or
        unit is ``NO_DATA``; a known one with nothing eligible yet returns ``None``.
        """
        matching = [
            f for f in facts if (f.taxonomy, f.concept, f.unit) == (taxonomy, concept, unit)
        ]
        if not matching:
            raise SourceError(
                ErrorCode.NO_DATA, f"no {taxonomy}:{concept} facts in {unit!r} for this company"
            )
        eligible: list[tuple[datetime, str, int, XbrlFact]] = []
        for fact in matching:
            accepted = availability.get(fact.accession)
            if fact.period == period and accepted is not None and accepted <= cutoff:
                eligible.append((accepted, fact.accession, fact.index, fact))
        if not eligible:
            return None
        return max(eligible, key=lambda entry: entry[:3])[3]

    def ingest_fact(
        self, fact: XbrlFact, body: bytes, *, cik: str, accepted_at: datetime | None
    ) -> tuple[EvidenceDocument, EvidenceSpan, str]:
        """Preserve the payload and make the fact citable as an exact span.

        Each selected fact becomes its own document version, available from its accession's
        acceptance time. Every filing of one (concept, unit, period) shares a source family, so
        :func:`~episalpha.evidence.temporal.select_current_versions` treats a restatement as a
        later version of the same thing.
        """
        payload_hash = self.object_store.put(body)
        text = extract_text(body)
        start, end = _locate(text, fact)
        ingested_at = self._now()
        if accepted_at is not None:
            available_at, basis = accepted_at, AvailabilityBasis.PROVIDER_VERIFIED
        else:
            available_at, basis = ingested_at, AvailabilityBasis.FIRST_CAPTURE
        lineage = _short_hash(fact.taxonomy, fact.concept, fact.unit, fact.start, fact.end)
        document_id = f"xbrl-{cik}-{fact.accession.replace('-', '')}-{lineage[:12]}"
        document = EvidenceDocument(
            document_id=document_id,
            source_uri=f"{COMPANYFACTS_URL.format(cik=cik)}#{fact.locator}",
            source_type="sec_xbrl_companyfacts",
            source_family_id=f"xbrl-{cik}-{lineage[:16]}",
            payload_hash=payload_hash,
            parsed_text_hash=parsed_text_hash(text),
            parser_version=PARSER_VERSION,
            published_at=_midnight(fact.filed),
            public_available_at=available_at,
            availability_basis=basis,
            ingested_at=ingested_at,
        )
        span = make_span(f"span.{document_id}", document_id, text, start, end, fact.locator)
        return document, span, text

    @staticmethod
    def to_numeric_fact(fact: XbrlFact) -> NumericFact:
        """The fact as a :class:`NumericFact`; an instant has ``period_start == period_end``.

        ``accounting_basis`` is the taxonomy, not the form: a 10-Q and a 10-K on the same
        taxonomy are comparable, and folding the form in would block every cross-period
        derivation. The form, fiscal period and accession go into ``source_context``.
        """
        return NumericFact(
            metric=f"{fact.taxonomy}:{fact.concept}",
            value=fact.value,
            unit=fact.unit,
            period_start=_midnight(fact.start or fact.end),
            period_end=_midnight(fact.end),
            accounting_basis=fact.taxonomy,
            source_context=(
                f"SEC XBRL {fact.form} {fact.fp or '-'} FY{fact.fy or '-'}, "
                f"accession {fact.accession}, filed {fact.filed.isoformat()}"
            ),
        )


def _fact(taxonomy: str, concept: str, unit: str, index: int, item: dict[str, Any]) -> XbrlFact:
    return XbrlFact(
        taxonomy=taxonomy,
        concept=concept,
        unit=unit,
        index=index,
        start=item.get("start"),
        end=item["end"],
        value=item["val"],
        accession=item["accn"],
        form=item["form"],
        filed=item["filed"],
        fy=int(item["fy"]) if item.get("fy") is not None else None,
        fp=item.get("fp"),
        frame=item.get("frame"),
    )


def _locate(text: str, fact: XbrlFact) -> tuple[int, int]:
    """Offsets of the fact's own JSON object in the stored text, verified by re-reading it."""
    position = text.find(f'"{fact.taxonomy}":{{')
    for key in (f'"{fact.concept}":{{', '"units":{', f'"{fact.unit}":['):
        if position < 0:
            break
        position = text.find(key, position)
    if position >= 0:
        for index, match in enumerate(_FLAT_OBJECT.finditer(text, position)):
            if index < fact.index:
                continue
            found = json.loads(match.group(), parse_float=Decimal, parse_int=Decimal)
            if found.get("accn") == fact.accession and found.get("val") == fact.value:
                return match.start(), match.end()
            break
    raise SourceError(
        ErrorCode.SOURCE_FAILED,
        f"cannot locate {fact.locator} ({fact.accession}) exactly in the stored text",
    )
