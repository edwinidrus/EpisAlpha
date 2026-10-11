"""Deterministic scripted runtime (plan M3-T01). Never live evidence.

:class:`FakeRuntime` replays one scenario from a JSON fixture, stage by stage. Every payload it
emits is labelled ``{"fixture": true, "source": "<fixture path>#<STAGE>"}``, so fake output can
never be mistaken for a live run (global constitution article 15). ``${RUN}`` in a fixture is
replaced with the run ID, so scripted later stages can cite host-assigned current-run IDs
(``<run_id>.<key>``).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from episalpha.contracts.research import RunState, RuntimeContext, StageResult, Usage
from episalpha.runtime.port import ExitReason
from episalpha.storage.objects import ObjectStore

# ponytail: the fake's scripts live with the test fixtures; the fake is a development and demo
# runtime, never a product path. Pass fixtures_dir to use another set.
DEFAULT_FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "runtime"


class Scenario(StrEnum):
    COMPLETION = "completion"
    ABSTENTION = "abstention"
    INVALID_REFERENCES = "invalid_references"
    PROVIDER_FAILURE = "provider_failure"
    TIMEOUT = "timeout"
    CANCELLATION = "cancellation"
    PARTIAL = "partial"
    REPAIRED = "repaired"


def _substitute(value: Any, run_id: str) -> Any:
    if isinstance(value, str):
        return value.replace("${RUN}", run_id)
    if isinstance(value, list):
        return [_substitute(item, run_id) for item in value]
    if isinstance(value, dict):
        return {key: _substitute(item, run_id) for key, item in value.items()}
    return value


class FakeRuntime:
    """Replays ``<fixtures_dir>/<scenario>.json``: ``{STAGE: {completed, exit_reason, payload,
    usage}}``, or a list of such entries for successive attempts. A stage the script does not
    mention ends as ``invalid_output``."""

    model_id = "fixture"

    def __init__(
        self,
        object_store: ObjectStore,
        scenario: Scenario,
        *,
        fixtures_dir: Path = DEFAULT_FIXTURES,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.object_store = object_store
        self.scenario = scenario
        self.path = fixtures_dir / f"{scenario.value}.json"
        self._script: dict[str, Any] = json.loads(self.path.read_text())
        self._now = now
        self._cancelled = False
        self._attempts: dict[str, int] = {}

    def cancel(self) -> None:
        self._cancelled = True

    def run_stage(self, stage: RunState, context: RuntimeContext) -> StageResult:
        started = self._now()
        spec = self._script.get(stage.value)
        if isinstance(spec, list):  # several scripted attempts, consumed in order
            attempt = self._attempts.get(stage.value, 0)
            self._attempts[stage.value] = attempt + 1
            spec = spec[min(attempt, len(spec) - 1)]
        if self._cancelled:
            spec = {"completed": False, "exit_reason": ExitReason.CANCELLED.value, "payload": None}
        elif spec is None:
            spec = {"completed": False, "exit_reason": ExitReason.INVALID_OUTPUT.value}
        payload_hash = None
        if spec.get("payload") is not None:
            payload = _substitute(spec["payload"], context.run_id)
            payload["fixture"] = True
            payload["source"] = f"{self._label()}#{stage.value}"
            encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
            payload_hash = self.object_store.put(encoded)
        if spec.get("exit_reason") == ExitReason.CANCELLED.value:
            self._cancelled = True
        usage = spec.get("usage", {})
        return StageResult(
            stage=stage,
            completed=bool(spec["completed"]),
            exit_reason=ExitReason(spec["exit_reason"]).value,
            candidate_payload_hash=payload_hash,
            usage=Usage(
                model_requests=int(usage.get("model_requests", 0)),
                tool_calls=int(usage.get("tool_calls", 0)),
            ),
            started_at=started,
            ended_at=self._now(),
        )

    def _label(self) -> str:
        root = DEFAULT_FIXTURES.parents[2]
        try:
            return self.path.resolve().relative_to(root).as_posix()
        except ValueError:
            return self.path.as_posix()
