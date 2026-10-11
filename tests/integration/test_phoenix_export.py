"""Live check that spans reach the local Arize Phoenix (M0-T07, amendment A14).

Needs the container from ``observability/compose.yaml``::

    docker compose -f observability/compose.yaml up -d
    uv run pytest -q -m live tests/integration/test_phoenix_export.py

Spans are read back through Phoenix's REST API,
``GET /v1/projects/{project}/spans/otlpv1?trace_id=...`` (route checked in the pinned image's
``phoenix/server/api/routers/v1/spans.py``). Synthetic traces go to a separate project,
``episalpha-tests``, so they never mix with real runs in the ``episalpha`` project.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import pytest

from episalpha.observability import (
    SpanKind,
    bind_run,
    configure_tracing,
    shutdown_tracing,
    span,
    trace_id_hex,
    trace_url,
)
from episalpha.settings import Settings

pytestmark = pytest.mark.live

PHOENIX = "http://127.0.0.1:6006"
PROJECT = "episalpha-tests"
SECRET = f"phoenix-test-secret-{uuid.uuid4().hex}"


def get(url: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:  # noqa: S310 - loopback only
            return response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()


@pytest.fixture(autouse=True)
def phoenix_running() -> None:
    try:
        get(f"{PHOENIX}/healthz")
    except OSError:
        pytest.skip("Phoenix is not running: docker compose -f observability/compose.yaml up -d")


def test_one_redacted_trace_tree_reaches_phoenix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TEST_SECRET", SECRET)
    settings = Settings.model_validate(
        {
            "paths": {"project_root": tmp_path, "data_root": tmp_path / "data"},
            "provider": {"api_key_env": "ENV:TEST_SECRET"},
            "observability": {
                "otlp_endpoint": f"{PHOENIX}/v1/traces",
                "project_name": PROJECT,
            },
        }
    )
    provider = configure_tracing(settings)
    try:
        run_id = f"run_{uuid.uuid4().hex[:12]}"
        with bind_run(run_id), span("research.run", SpanKind.CHAIN) as root:
            with span(
                "model.call",
                SpanKind.LLM,
                **{"input.value": f"synthetic prompt carrying {SECRET}", "llm.model_name": "fx"},
            ):
                pass
            with span("tool.search_evidence", SpanKind.RETRIEVER, hits=2):
                pass
        assert provider.force_flush(10_000)
        trace_id = trace_id_hex(root)
        link = trace_url(trace_id)
    finally:
        shutdown_tracing()

    body = ""
    spans: list[dict[str, object]] = []
    for _ in range(20):
        status, body = get(f"{PHOENIX}/v1/projects/{PROJECT}/spans/otlpv1?trace_id={trace_id}")
        if status == 200:
            spans = json.loads(body)["data"]
            if len(spans) == 3:
                break
        time.sleep(0.5)

    assert sorted(str(item["name"]) for item in spans) == [
        "model.call",
        "research.run",
        "tool.search_evidence",
    ]
    for kind in ("CHAIN", "LLM", "RETRIEVER"):
        assert kind in body
    assert run_id in body
    # Phoenix receives full content, but never a secret.
    assert "synthetic prompt carrying ***" in body
    assert SECRET not in body

    # The JSONL fallback got the same trace, without the content.
    jsonl = (tmp_path / "data" / "logs" / "spans.jsonl").read_text()
    assert jsonl.count(trace_id) == 3
    assert "synthetic prompt" not in jsonl
    assert SECRET not in jsonl

    # The UI link resolves (Phoenix answers with the SPA or a redirect, never 404).
    assert link == f"{PHOENIX}/redirects/traces/{trace_id}"
    status, _ = get(link)
    assert status == 200
