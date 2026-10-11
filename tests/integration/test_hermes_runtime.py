"""Live: three research stages on pinned Hermes through the relay (M3-T03).

Needs the pinned Hermes environment (``.episalpha/vendor/hermes-venv``, see the M3-T01 journal),
the route credential, and owner approval for about 7 model requests::

    set -a; . ./.env; set +a
    uv run pytest -q -m live tests/integration/test_hermes_runtime.py

Set ``EPISALPHA_LIVE_REPORT=<path>`` to keep a JSON summary for the journal. The snapshot is the
SYNTHETIC fixture; nothing here is evidence about a real company.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

import pytest
from fixtures.synthetic_knowledge import DEMAND_SPAN, REVENUE_SPAN
from runtime.test_tools import make_host

from episalpha.contracts.research import RunState, RuntimeContext
from episalpha.observability import (
    SpanKind,
    bind_run,
    configure_tracing,
    shutdown_tracing,
    span,
    trace_id_hex,
)
from episalpha.runtime.candidates import (
    CritiqueCandidate,
    ResearchCandidate,
    ThesisCandidate,
    parse_candidate,
)
from episalpha.runtime.hermes import HermesRuntime, LocalLauncher, WorkerLauncher, load_harness
from episalpha.runtime.model_relay import ModelRelay, RelayServer
from episalpha.runtime.sandbox import SandboxConfig, SandboxLauncher
from episalpha.settings import load_settings
from episalpha.storage.objects import ObjectStore

pytestmark = pytest.mark.live

ROOT = Path(__file__).resolve().parents[2]
VENDOR = ROOT / ".episalpha" / "vendor"
HERMES_PYTHON = VENDOR / "hermes-venv" / "bin" / "python"
HERMES_SOURCE = VENDOR / "hermes-agent"
SNAPSHOT_SPANS = {REVENUE_SPAN.span_id, DEMAND_SPAN.span_id}
QUESTION = "Did the issuer signal weaker demand, and what revenue did it report?"


def brief(stage: RunState, context: RuntimeContext, records: dict[str, Any]) -> str:
    lines = [
        f"RUN_ID: {context.run_id}",
        f"Instrument: synthetic-issuer.eq (ticker SYN). Research cutoff: "
        f"{context.research_cutoff.isoformat()}. Mode: historical reconstruction.",
        f"Question: {QUESTION}",
        f"You may make at most {records['cap']} model turns in this stage; the last one must "
        "be your submit call.",
    ]
    if stage is not RunState.RESEARCHING:
        lines.append("Validated records (cite these IDs exactly):")
        lines += [f"- {key}: {text}" for key, text in records["validated"].items()]
    if stage is RunState.SYNTHESIZING:
        lines.append(f"Critique: {json.dumps(records['critique'])}")
    return "\n".join(lines)


@pytest.mark.skipif(not HERMES_PYTHON.exists(), reason="pinned Hermes venv not installed")
def test_three_live_stages(tmp_path: Path) -> None:
    run_three_stages(
        tmp_path,
        LocalLauncher(
            [str(HERMES_PYTHON), str(ROOT / "worker" / "hermes_stage.py")], cwd=HERMES_SOURCE
        ),
    )


def test_three_live_stages_in_the_container(tmp_path: Path) -> None:
    """G3: a real-provider run with the worker inside the hardened container (M3-T04)."""
    image = json.loads((ROOT / "config" / "runtime.lock.json").read_text())["hermes"].get(
        "worker_image", {}
    )
    if not image.get("id") or shutil.which("docker") is None:
        pytest.skip("Docker or the pinned worker image is not available")
    run_three_stages(tmp_path, SandboxLauncher(SandboxConfig(image=image["id"])))


def run_three_stages(tmp_path: Path, launcher: WorkerLauncher) -> None:
    settings = load_settings(ROOT / "config" / "demo.toml")
    if settings.provider.credential() is None:
        pytest.skip("route credential not exported; source .env first")
    observability = settings.observability.model_copy(
        update={
            "otlp_endpoint": "http://127.0.0.1:6006/v1/traces",
            "project_name": "episalpha-tests",
        }
    )
    configure_tracing(
        settings.model_copy(
            update={
                "observability": observability,
                "paths": settings.paths.model_copy(update={"data_root": tmp_path / "data"}),
            }
        )
    )
    lock = json.loads((ROOT / "config" / "runtime.lock.json").read_text())["model_route"]
    token = secrets.token_hex(16)
    relay = ModelRelay(
        settings.provider,
        settings.limits,
        token,
        no_fallbacks=bool(lock["observed_capabilities"].get("no_fallbacks_accepted")),
        deadline=time.monotonic() + settings.limits.run_wall_time_seconds,
    )
    server = RelayServer(relay, host=launcher.bind_host, port=0)
    server.start()
    records: dict[str, Any] = {"validated": {}, "critique": {}, "cap": 0}
    run_id = f"run.live-{uuid.uuid4().hex[:8]}"

    def brief_for(stage: RunState, context: RuntimeContext) -> str:
        from episalpha.runtime.hermes import stage_cap

        records["cap"] = stage_cap(settings.limits, stage)
        return brief(stage, context, records)

    runtime = HermesRuntime(
        harness=load_harness(ROOT / "harnesses" / "baseline"),
        relay=relay,
        relay_port=server.port,
        relay_token=token,
        model_id=str(settings.provider.model_id),
        limits=settings.limits,
        object_store=ObjectStore(tmp_path / "objects"),
        tools_for=lambda stage, context: make_host(),
        brief_for=brief_for,
        launcher=launcher,
        work_dir=tmp_path / "work",
    )
    base = make_host().context.model_copy(update={"run_id": run_id})
    candidates: dict[RunState, Any] = {}
    try:
        with bind_run(run_id), span("research.run", SpanKind.CHAIN) as root:
            for stage in (RunState.RESEARCHING, RunState.CRITIQUING, RunState.SYNTHESIZING):
                context = base.model_copy(
                    update={
                        "stage": stage,
                        "remaining_model_requests": settings.limits.max_model_requests
                        - relay.requests_used,
                    }
                )
                result = runtime.run_stage(stage, context)
                assert result.completed, (stage, result.exit_reason, runtime.reports[-1])
                assert result.candidate_payload_hash is not None
                payload = json.loads(runtime.object_store.get(result.candidate_payload_hash))
                candidates[stage] = parse_candidate(stage, payload)
                if stage is RunState.RESEARCHING:
                    research = candidates[stage]
                    assert isinstance(research, ResearchCandidate)
                    for claim in research.claims:
                        if set(claim.span_ids) <= SNAPSHOT_SPANS:
                            records["validated"][f"{run_id}.{claim.key}"] = claim.statement
                    for hypothesis in research.hypotheses:
                        records["validated"][f"{run_id}.{hypothesis.key}"] = (
                            f"(hypothesis) {hypothesis.mechanism}"
                        )
                if stage is RunState.CRITIQUING:
                    critique_candidate = candidates[stage]
                    assert isinstance(critique_candidate, CritiqueCandidate)
                    for claim in critique_candidate.counter_claims:
                        if set(claim.span_ids) <= SNAPSHOT_SPANS:
                            records["validated"][f"{run_id}.{claim.key}"] = (
                                f"(counter-evidence) {claim.statement}"
                            )
                    records["critique"] = {
                        "contradictions": payload.get("contradictions", []),
                        "missing_information": payload.get("missing_information", []),
                    }
            trace_id = trace_id_hex(root)
    finally:
        server.stop()
        shutdown_tracing()

    research = candidates[RunState.RESEARCHING]
    critique = candidates[RunState.CRITIQUING]
    thesis = candidates[RunState.SYNTHESIZING]
    assert isinstance(research, ResearchCandidate)
    assert isinstance(critique, CritiqueCandidate)
    assert isinstance(thesis, ThesisCandidate)
    cited = {span_id for claim in research.claims for span_id in claim.span_ids}
    assert cited, "the researcher cited no spans"
    assert cited <= SNAPSHOT_SPANS, f"invented span IDs: {cited - SNAPSHOT_SPANS}"
    known = set(records["validated"])
    referenced = {ref for a in thesis.assertions for ref in (*a.claim_ids, *a.hypothesis_ids)}
    allowed = known | set(make_host().context.snapshot.permitted_claim_ids)
    assert referenced <= allowed, referenced - allowed
    for report in runtime.reports:
        assert report.worker["effective_tools"] == sorted(report.worker["effective_tools"])
        assert report.worker["error"] is None
        assert report.worker["fallback_model"] is None
        assert report.worker["learning_writes"] == []
    assert relay.requests_used == sum(report.requests for report in runtime.reports)
    assert relay.requests_used <= settings.limits.max_model_requests

    summary = {
        "run_id": run_id,
        "trace_id": trace_id,
        "launcher": type(launcher).__name__,
        "harness_hash": runtime.harness.harness_hash,
        "skill_set_hash": runtime.harness.skill_set_hash,
        "served_by": relay.served_by,
        "usage": relay.usage.model_dump(),
        "stages": [
            {
                "stage": r.stage.value,
                "exit_reason": r.exit_reason,
                "requests": r.requests,
                "tool_calls": r.tool_calls,
                "seconds": r.seconds,
                "effective_tools": r.worker.get("effective_tools"),
                "worker_tool_calls": r.worker.get("tool_calls"),
                "interrupted": r.worker.get("interrupted"),
                "home_files": r.worker.get("home_files"),
                "learning_writes": r.worker.get("learning_writes"),
            }
            for r in runtime.reports
        ],
        "research": research.model_dump(mode="json"),
        "critique": critique.model_dump(mode="json"),
        "thesis": thesis.model_dump(mode="json"),
    }
    if os.environ.get("EPISALPHA_LIVE_REPORT"):
        Path(os.environ["EPISALPHA_LIVE_REPORT"]).write_text(json.dumps(summary, indent=2))
