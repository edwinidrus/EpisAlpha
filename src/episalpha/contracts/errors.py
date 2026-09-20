"""Frozen error codes (plan section M1-T02).

Each code answers a different question, and collapsing two of them would hide exactly the
distinction the product exists to preserve: "we found nothing" is not "we could not look".
"""

from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    NO_DATA = "NO_DATA"
    """The source was reachable and had nothing. An honest empty answer."""

    SOURCE_FAILED = "SOURCE_FAILED"
    """The source could not be consulted. Never report this as an absence of information."""

    INVALID_REQUEST = "INVALID_REQUEST"
    """The request itself was malformed or inadmissible."""

    INVALID_OUTPUT = "INVALID_OUTPUT"
    """A candidate failed structural validation and bounded repair did not fix it."""

    INELIGIBLE_EVIDENCE = "INELIGIBLE_EVIDENCE"
    """Evidence exists but does not qualify at this research cutoff."""

    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    """A time, request, tool-call or token budget from settings ran out."""

    NOT_AUTHORIZED = "NOT_AUTHORIZED"
    """A component attempted something outside its trust zone."""

    INTEGRITY_ERROR = "INTEGRITY_ERROR"
    """A stored artifact does not match its recorded hash."""


class EpisAlphaError(Exception):
    """Base error carrying a frozen code, so callers branch on the code and not on text."""

    code: ErrorCode

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code

    def __str__(self) -> str:
        return f"{self.code.value}: {super().__str__()}"


class InvalidTransitionError(EpisAlphaError):
    """A run was asked to move to a state the lifecycle does not allow."""

    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.INVALID_REQUEST, message)
