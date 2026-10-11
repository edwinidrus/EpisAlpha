"""End-of-day price context (plan M2-T03, amendments A4 and A6).

v0.1 uses prices as *display context only*. That restriction is enforced here rather than left
to discipline: the free Alpha Vantage tier returns an **unadjusted** close, so a split would
manufacture a fake return, and :meth:`PriceSeries.simple_return` refuses to compute one from an
unadjusted series instead of quietly returning a wrong number.

The connector takes a transport callable, so the default test suite drives it from recorded
fixtures with no network and no credentials.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Self

from opentelemetry.trace import Span
from pydantic import Field, model_validator

from episalpha.contracts.errors import EpisAlphaError, ErrorCode
from episalpha.contracts.knowledge import Contract, DecimalString, Identifier, UtcTimestamp
from episalpha.observability import SpanKind, span

DAILY_FUNCTION = "TIME_SERIES_DAILY"
ADJUSTED_FUNCTION = "TIME_SERIES_DAILY_ADJUSTED"
"""Premium as of the M0-T03 probe. Named so a future upgrade has an obvious hook."""

MIN_REQUEST_SPACING_SECONDS = 1.0
"""Amendment A4: the free tier refuses back-to-back calls regardless of the daily quota."""

# Alpha Vantage answers a throttle, an entitlement refusal and an unknown symbol with HTTP 200
# and one of these keys. Treating any of them as "no data" would turn an outage into a
# confident empty answer, which is exactly what plan section 3.6 forbids.
_REFUSAL_KEYS = ("Information", "Note", "Error Message")


class SourceError(EpisAlphaError):
    """A source could not be consulted, or answered with a refusal."""


class AdjustmentBasis(StrEnum):
    UNADJUSTED = "unadjusted"
    SPLIT_AND_DIVIDEND_ADJUSTED = "split_and_dividend_adjusted"


class PricePoint(Contract):
    """One end-of-day observation."""

    trade_date: date
    close: DecimalString
    volume: int | None = None


class PriceSeries(Contract):
    """A dated price path with everything needed to know what it does and does not mean."""

    instrument_id: Identifier
    source_id: Identifier
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    adjustment_basis: AdjustmentBasis
    points: tuple[PricePoint, ...] = Field(min_length=1)
    fetched_at: UtcTimestamp

    @model_validator(mode="after")
    def _dates_are_ordered_and_unique(self) -> Self:
        dates = [point.trade_date for point in self.points]
        if len(set(dates)) != len(dates):
            raise ValueError("a trade date appears more than once")
        if dates != sorted(dates):
            raise ValueError("points must be ordered oldest first")
        return self

    @property
    def is_adjusted(self) -> bool:
        return self.adjustment_basis is AdjustmentBasis.SPLIT_AND_DIVIDEND_ADJUSTED

    def close_on(self, on: date) -> PricePoint | None:
        return next((p for p in self.points if p.trade_date == on), None)

    def as_of(self, cutoff: date) -> PriceSeries | None:
        """The series truncated at a research cutoff. ``None`` when nothing qualifies."""
        eligible = tuple(p for p in self.points if p.trade_date <= cutoff)
        if not eligible:
            return None
        return self.model_copy(update={"points": eligible})

    def simple_return(self, start: date, end: date) -> Decimal:
        """A multi-day return — only from an adjusted series.

        Refusing here is the point (amendment A6). On an unadjusted series a split or dividend
        produces a return that looks real and is not, and no label downstream can undo a number
        that has already been computed and shown.
        """
        if not self.is_adjusted:
            raise SourceError(
                ErrorCode.INTEGRITY_ERROR,
                f"series for {self.instrument_id!r} is {self.adjustment_basis.value!r}; a "
                "multi-day return cannot be computed from it because a split or dividend would "
                "manufacture a false return. Obtain an adjusted series first",
            )
        first, last = self.close_on(start), self.close_on(end)
        if first is None or last is None:
            missing = start if first is None else end
            raise SourceError(ErrorCode.NO_DATA, f"no close on {missing.isoformat()}")
        return (last.close - first.close) / first.close


Transport = Callable[[dict[str, str]], str]
"""Takes query parameters, returns the raw response body. Injected so tests stay offline."""


@contextmanager
def fetch_span(source_id: str, operation: str, host: str | None) -> Iterator[Span]:
    """One ``connector.fetch`` span per external call (M2 constitution article 10).

    Metadata only: source, operation, host, outcome, size and hash. Never the body, the query
    string, the full URL or a key; payloads are canonical in the object store, by hash.
    """
    attributes = {
        "episalpha.source_id": source_id,
        "episalpha.operation": operation,
        "server.address": host,
    }
    with span("connector.fetch", SpanKind.CHAIN, **attributes) as current:
        try:
            yield current
        except SourceError as error:
            current.set_attribute("episalpha.outcome", error.code.value)
            raise
        current.set_attribute("episalpha.outcome", "ok")


def record_payload(current: Span, body: bytes | str) -> None:
    data = body.encode("utf-8") if isinstance(body, str) else body
    current.set_attribute("episalpha.bytes", len(data))
    current.set_attribute("episalpha.payload_hash", hashlib.sha256(data).hexdigest())


class AlphaVantagePrices:
    """Daily price connector.

    It never infers an investment conclusion and never substitutes today's data for a
    historical request; callers narrow a series with :meth:`PriceSeries.as_of`.
    """

    source_id = "alpha_vantage"
    host = "www.alphavantage.co"

    def __init__(
        self,
        transport: Transport,
        *,
        api_key: str | None = None,
        currency: str = "USD",
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.transport = transport
        self.api_key = api_key
        self.currency = currency
        self._now = now

    def daily(self, instrument_id: str, symbol: str) -> PriceSeries:
        """Fetch the daily series for one symbol.

        Raises :class:`SourceError` with ``SOURCE_FAILED`` when the source refuses, and with
        ``NO_DATA`` when it answers properly but has nothing. Those are different facts and the
        research workflow treats them differently.
        """
        parameters = {
            "function": DAILY_FUNCTION,
            "symbol": symbol,
            "outputsize": "compact",
        }
        if self.api_key:
            parameters["apikey"] = self.api_key

        with fetch_span(self.source_id, "daily", self.host) as current:
            try:
                body = self.transport(parameters)
            except SourceError:
                raise
            except Exception as error:  # transport-level failure is never an absence of data
                raise SourceError(
                    ErrorCode.SOURCE_FAILED, f"{self.source_id} transport failed: {error}"
                ) from error
            record_payload(current, body)
            return self._parse(instrument_id, symbol, body)

    def _parse(self, instrument_id: str, symbol: str, body: str) -> PriceSeries:
        try:
            document: dict[str, Any] = json.loads(body)
        except json.JSONDecodeError as error:
            raise SourceError(
                ErrorCode.SOURCE_FAILED, f"{self.source_id} returned unparseable content"
            ) from error

        for key in _REFUSAL_KEYS:
            if key in document:
                raise SourceError(
                    ErrorCode.SOURCE_FAILED,
                    f"{self.source_id} refused the request for {symbol!r} "
                    f"({key}: {str(document[key])[:160]}). This is a refusal, not an absence "
                    "of data",
                )

        series = document.get("Time Series (Daily)")
        if not isinstance(series, dict) or not series:
            raise SourceError(
                ErrorCode.NO_DATA, f"{self.source_id} has no daily series for {symbol!r}"
            )

        points = tuple(
            PricePoint(
                trade_date=date.fromisoformat(day),
                close=values["4. close"],
                volume=int(values["5. volume"]) if "5. volume" in values else None,
            )
            for day, values in sorted(series.items())
        )
        return PriceSeries(
            instrument_id=instrument_id,
            source_id=self.source_id,
            currency=self.currency,
            # The free endpoint is unadjusted. Recording the truth here is what lets
            # simple_return() refuse later.
            adjustment_basis=AdjustmentBasis.UNADJUSTED,
            points=points,
            fetched_at=self._now(),
        )
