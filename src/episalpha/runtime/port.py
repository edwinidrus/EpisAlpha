"""The research runtime port (plan M3-T01, section 3.2).

The host drives one stage at a time through :class:`ResearchRuntimePort`. A runtime returns a
:class:`~episalpha.contracts.research.StageResult`; the candidate payload itself goes into the
content-addressed object store, and ``candidate_payload_hash`` points at it. The runtime only
*proposes*: the host validates, assigns canonical IDs and decides the run state (M3
constitution article 1).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Protocol

from pydantic import Field

from episalpha.contracts.errors import ErrorCode
from episalpha.contracts.knowledge import ContentHash, Contract
from episalpha.contracts.research import RunState, RuntimeContext, StageResult


class ExitReason(StrEnum):
    """Why a stage ended. The runner maps these to run states; none of them is an abstention."""

    COMPLETED = "completed"
    PARTIAL = "partial"
    PROVIDER_FAILURE = "provider_failure"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    BUDGET_EXCEEDED = "budget_exceeded"
    INVALID_OUTPUT = "invalid_output"


class ResearchRuntimePort(Protocol):
    """What the runner needs from any runtime, fake or Hermes."""

    def run_stage(self, stage: RunState, context: RuntimeContext) -> StageResult:
        """Run one stage within ``context``'s budgets and return what happened."""
        ...

    def cancel(self) -> None:
        """Request cancellation. A stage in flight ends with ``ExitReason.CANCELLED``."""
        ...


class ToolResult(Contract):
    """One typed tool answer. ``result_hash`` covers ``ok``, ``payload`` and ``error_code``."""

    ok: bool
    payload: dict[str, Any]
    error_code: ErrorCode | None = None
    result_hash: ContentHash
    bytes: int = Field(ge=0)
