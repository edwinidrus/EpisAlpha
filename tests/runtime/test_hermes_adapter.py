"""M3-T03 — the Hermes runtime's host side, driven by a stdlib fake worker (no Hermes, no model).

The fake worker (``tests/fixtures/runtime/fake_worker.py``) speaks to the real host MCP server
over HTTP, exactly as the Hermes worker does, so the protocol between them is exercised.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from runtime.test_tools import make_host

from episalpha.contracts.research import RunState, RuntimeContext
from episalpha.observability import configure_tracing, shutdown_tracing
from episalpha.runtime.hermes import (
    EMPTY_SKILL_SET,
    HermesRuntime,
    LocalLauncher,
    load_harness,
    read_worker_json,
)
from episalpha.runtime.model_relay import ModelRelay
from episalpha.runtime.port import ExitReason
from episalpha.settings import Limits, ProviderRoute, Settings
from episalpha.storage.objects import ObjectStore

ROOT = Path(__file__).resolve().parents[2]
FAKE_WORKER = ROOT / "tests" / "fixtures" / "runtime" / "fake_worker.py"
HARNESS = ROOT / "harnesses" / "baseline"
NOW = datetime(2026, 10, 11, 6, 0, tzinfo=UTC)


def fixture_payload(stage: RunState) -> dict[str, Any]:
    script = json.loads((ROOT / "tests" / "fixtures" / "runtime" / "completion.json").read_text())
    payload = script[stage.value]["payload"]
    return json.loads(json.dumps(payload).replace("${RUN}", "run.0001"))  # type: ignore[no-any-return]


@pytest.fixture
def make_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    monkeypatch.setenv("RELAY_TEST_KEY", "sk-test-provider-key-never-in-worker")

    def factory(mode: str, stage: RunState = RunState.RESEARCHING) -> HermesRuntime:
        payload_file = tmp_path / f"payload-{stage.value}.json"
        payload_file.write_text(json.dumps(fixture_payload(stage)))
        relay = ModelRelay(
            ProviderRoute(
                model_id="m/x:free",
                endpoint_url="https://openrouter.ai/api/v1",
                api_key_env="ENV:RELAY_TEST_KEY",
            ),
            Limits(),
            "relay-token",
        )
        return HermesRuntime(
            harness=load_harness(HARNESS),
            relay=relay,
            relay_port=9,
            relay_token="relay-token",
            model_id="m/x:free",
            limits=Limits(),
            object_store=ObjectStore(tmp_path / "objects"),
            tools_for=lambda stage, context: make_host(),
            brief_for=lambda stage, context: f"BRIEF {stage.value} for {context.run_id}",
            launcher=LocalLauncher([sys.executable, str(FAKE_WORKER)]),
            work_dir=tmp_path / "work",
            worker_env={"FAKE_WORKER_MODE": mode, "FAKE_WORKER_PAYLOAD": str(payload_file)},
            now=lambda: NOW,
        )

    yield factory


def context(stage: RunState, wall: int = 60) -> RuntimeContext:
    return make_host().context.model_copy(
        update={"stage": stage, "remaining_wall_time_seconds": wall}
    )


def spec_of(runtime: HermesRuntime, stage: RunState) -> dict[str, Any]:
    path = runtime.work_dir / "run.0001" / stage.value.lower() / "spec.json"
    return json.loads(path.read_text())  # type: ignore[no-any-return]


def test_valid_submission_completes(make_runtime: Any) -> None:
    runtime = make_runtime("submit_valid")
    result = runtime.run_stage(RunState.RESEARCHING, context(RunState.RESEARCHING))
    assert result.completed, result.exit_reason
    assert result.exit_reason == ExitReason.COMPLETED
    assert result.candidate_payload_hash is not None
    stored = json.loads(runtime.object_store.get(result.candidate_payload_hash))
    assert stored["claims"][0]["key"] == "c1"
    assert result.usage.tool_calls == 1
    assert len(result.tool_event_hashes) == 1
    assert result.usage.model_requests == 0


def test_malformed_submission_is_invalid_output_and_preserved(make_runtime: Any) -> None:
    runtime = make_runtime("submit_malformed", RunState.SYNTHESIZING)
    result = runtime.run_stage(RunState.SYNTHESIZING, context(RunState.SYNTHESIZING))
    assert not result.completed
    assert result.exit_reason.startswith("invalid_output: ")
    assert result.candidate_payload_hash is not None
    assert json.loads(runtime.object_store.get(result.candidate_payload_hash)) == {
        "stance": "nonsense"
    }


def test_allowlist_mismatch_aborts(make_runtime: Any) -> None:
    result = make_runtime("mismatch").run_stage(RunState.RESEARCHING, context(RunState.RESEARCHING))
    assert not result.completed
    assert result.exit_reason == "invalid_output: TOOL_ALLOWLIST_MISMATCH"


def test_no_submission_is_invalid_output(make_runtime: Any) -> None:
    result = make_runtime("no_submit").run_stage(RunState.CRITIQUING, context(RunState.CRITIQUING))
    assert result.exit_reason == "invalid_output: no submission"


def test_worker_timeout_is_killed(make_runtime: Any) -> None:
    result = make_runtime("sleep").run_stage(
        RunState.RESEARCHING, context(RunState.RESEARCHING, wall=1)
    )
    assert result.exit_reason == ExitReason.TIMEOUT


def test_cancel_before_a_stage(make_runtime: Any) -> None:
    runtime = make_runtime("submit_valid")
    runtime.cancel()
    result = runtime.run_stage(RunState.RESEARCHING, context(RunState.RESEARCHING))
    assert result.exit_reason == ExitReason.CANCELLED


def test_fresh_session_and_brief_only_per_stage(make_runtime: Any) -> None:
    runtime = make_runtime("no_submit")
    runtime.run_stage(RunState.RESEARCHING, context(RunState.RESEARCHING))
    runtime.run_stage(RunState.CRITIQUING, context(RunState.CRITIQUING))
    research = spec_of(runtime, RunState.RESEARCHING)
    critic = spec_of(runtime, RunState.CRITIQUING)
    assert research["session_id"] != critic["session_id"]
    assert critic["user_prompt"] == "BRIEF CRITIQUING for run.0001"
    assert set(critic) == {
        "stage",
        "session_id",
        "system_prompt",
        "user_prompt",
        "relay_url",
        "relay_token",
        "mcp_url",
        "mcp_token",
        "model",
        "max_iterations",
        "max_tokens",
        "allowed_tools",
        "submit_tool",
    }
    assert critic["max_iterations"] == Limits().max_critic_requests
    assert critic["submit_tool"] == "mcp__episalpha__submit_critique"
    assert "mcp__episalpha__propose_skill" not in critic["allowed_tools"]


def test_worker_never_sees_the_provider_key_or_fallbacks(make_runtime: Any) -> None:
    runtime = make_runtime("no_submit")
    runtime.run_stage(RunState.RESEARCHING, context(RunState.RESEARCHING))
    report = runtime.reports[0].worker
    assert "RELAY_TEST_KEY" not in report["env_keys"]
    assert "openrouter_api_key" not in report["env_keys"]
    spec_text = json.dumps(spec_of(runtime, RunState.RESEARCHING))
    assert "sk-test-provider-key" not in spec_text
    assert "fallback" not in spec_text
    assert report["learning_writes"] == []
    assert report["home_files"] == ["config.yaml"]


def test_stage_span_carries_the_harness_hash(make_runtime: Any, tmp_path: Path) -> None:
    exporter = InMemorySpanExporter()
    settings = Settings.model_validate(
        {"paths": {"project_root": tmp_path, "data_root": tmp_path / "data"}}
    )
    configure_tracing(settings, extra_exporter=exporter)
    try:
        runtime = make_runtime("submit_valid")
        runtime.run_stage(RunState.RESEARCHING, context(RunState.RESEARCHING))
    finally:
        shutdown_tracing()
    spans = {item.name: item for item in exporter.get_finished_spans()}
    stage = spans["sandbox.run"]
    assert stage.attributes is not None
    assert stage.attributes["openinference.span.kind"] == "CHAIN"
    assert stage.attributes["episalpha.stage"] == "RESEARCHING"
    assert stage.attributes["episalpha.harness_hash"] == runtime.harness.harness_hash
    tool = spans["tool.search_evidence"]
    assert tool.parent is not None and tool.parent.span_id == stage.context.span_id
    assert spans["tool.submit_research"].parent is not None


def test_harness_hash_is_stable_and_covers_the_skill_set(tmp_path: Path) -> None:
    first, second = load_harness(HARNESS), load_harness(HARNESS)
    assert first.harness_hash == second.harness_hash
    assert first.skill_set_hash == EMPTY_SKILL_SET
    assert "Contradiction search" not in first.prompts[RunState.CRITIQUING]
    skills = tmp_path / "skills"
    skills.mkdir()
    (skills / "one.md").write_text("procedure")
    with_skill = load_harness(HARNESS, skills_dir=skills)
    assert with_skill.harness_hash != first.harness_hash


def test_contradiction_search_flag_changes_the_critic_prompt(tmp_path: Path) -> None:
    copy = tmp_path / "challenger"
    copy.mkdir()
    for path in HARNESS.iterdir():
        (copy / path.name).write_bytes(path.read_bytes())
    (copy / "config.json").write_text('{"schema_version": "1", "contradiction_search": true}')
    challenger = load_harness(copy)
    assert "Contradiction search" in challenger.prompts[RunState.CRITIQUING]
    assert challenger.harness_hash != load_harness(HARNESS).harness_hash


def test_worker_output_is_read_as_hostile_input(tmp_path: Path) -> None:
    real = tmp_path / "real.json"
    real.write_text('{"ok": true}')
    assert read_worker_json(real) == {"ok": True}
    link = tmp_path / "link.json"
    os.symlink(real, link)
    with pytest.raises(OSError):
        read_worker_json(link)
    big = tmp_path / "big.json"
    big.write_text(json.dumps({"x": "y" * 100}))
    with pytest.raises(ValueError, match="cap"):
        read_worker_json(big, max_bytes=50)
    listing = tmp_path / "list.json"
    listing.write_text("[1, 2]")
    with pytest.raises(ValueError, match="object"):
        read_worker_json(listing)


def test_a_persisted_conversation_is_flagged(make_runtime: Any) -> None:
    runtime = make_runtime("state_db")
    runtime.run_stage(RunState.RESEARCHING, context(RunState.RESEARCHING))
    report = runtime.reports[0].worker
    assert report["state_db_rows"] == 1
    assert report["learning_writes"] == ["state.db"]
