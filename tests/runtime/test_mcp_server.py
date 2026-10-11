"""M3-T02b — the host MCP tool server and the stage candidate schemas."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from runtime.test_tools import make_host

from episalpha.contracts.research import RunState
from episalpha.runtime.candidates import (
    CritiqueCandidate,
    ResearchCandidate,
    ThesisCandidate,
    parse_candidate,
    submit_schema,
)
from episalpha.runtime.mcp_server import McpToolServer, SubmissionSink, handle_rpc, stage_tools

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "runtime"
READ_TOOLS = {
    "resolve_instrument",
    "search_evidence",
    "get_evidence_span",
    "get_market_context",
    "get_support_and_contradictions",
    "get_numeric_facts",
    "compute_derivation",
}


def tools_for(stage: RunState) -> tuple[list[Any], SubmissionSink]:
    sink = SubmissionSink(stage)
    return stage_tools(make_host(), stage, sink), sink


def rpc(tools: list[Any], method: str, params: dict[str, Any] | None = None, id_: int = 1) -> Any:
    message: dict[str, Any] = {"jsonrpc": "2.0", "id": id_, "method": method}
    if params is not None:
        message["params"] = params
    return handle_rpc(tools, message)


def call(tools: list[Any], name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    reply = rpc(tools, "tools/call", {"name": name, "arguments": arguments})
    return reply["result"]  # type: ignore[no-any-return]


def body(result: dict[str, Any]) -> dict[str, Any]:
    return json.loads(result["content"][0]["text"])  # type: ignore[no-any-return]


# --- JSON-RPC subset -----------------------------------------------------------------------


def test_initialize_echoes_a_handshake_version() -> None:
    tools, _ = tools_for(RunState.RESEARCHING)
    reply = rpc(tools, "initialize", {"protocolVersion": "2025-11-25"})
    assert reply["result"]["protocolVersion"] == "2025-11-25"
    assert reply["result"]["capabilities"] == {"tools": {"listChanged": False}}
    newer = rpc(tools, "initialize", {"protocolVersion": "2099-01-01"})
    assert newer["result"]["protocolVersion"] == "2025-11-25"


def test_notifications_get_no_reply_and_unknown_methods_are_errors() -> None:
    tools, _ = tools_for(RunState.RESEARCHING)
    assert handle_rpc(tools, {"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    assert rpc(tools, "ping") == {"jsonrpc": "2.0", "id": 1, "result": {}}
    assert rpc(tools, "server/discover")["error"]["code"] == -32601


@pytest.mark.parametrize(
    ("stage", "expected"),
    [
        (RunState.RESEARCHING, READ_TOOLS | {"propose_skill", "submit_research"}),
        (RunState.CRITIQUING, READ_TOOLS | {"submit_critique"}),
        (
            RunState.SYNTHESIZING,
            {
                "get_evidence_span",
                "get_support_and_contradictions",
                "compute_derivation",
                "submit_thesis",
            },
        ),
    ],
)
def test_each_stage_exposes_exactly_its_tools(stage: RunState, expected: set[str]) -> None:
    tools, _ = tools_for(stage)
    listed = rpc(tools, "tools/list")["result"]["tools"]
    assert {tool["name"] for tool in listed} == expected
    for tool in listed:
        assert tool["inputSchema"]["type"] == "object"
        assert "$ref" not in json.dumps(tool["inputSchema"])


# --- tool calls ----------------------------------------------------------------------------


def test_read_tool_round_trip() -> None:
    tools, _ = tools_for(RunState.RESEARCHING)
    result = call(tools, "get_evidence_span", {"span_id": "synthetic-span.revenue"})
    assert result["isError"] is False
    assert body(result)["payload"]["quote"].startswith("Fourth quarter revenue")


def test_tool_refusal_is_an_mcp_error_result() -> None:
    tools, _ = tools_for(RunState.RESEARCHING)
    result = call(tools, "get_evidence_span", {"span_id": "synthetic-span.ghost"})
    assert result["isError"] is True
    assert body(result)["error_code"] == "NOT_AUTHORIZED"


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"span_id": 7},
        {"span_id": "synthetic-span.revenue", "cutoff": "2030-01-01"},
    ],
)
def test_bad_arguments_are_invalid_request(arguments: dict[str, Any]) -> None:
    tools, _ = tools_for(RunState.RESEARCHING)
    result = call(tools, "get_evidence_span", arguments)
    assert result["isError"] is True
    assert body(result)["error_code"] == "INVALID_REQUEST"


def test_unknown_or_other_stage_tool_is_rejected() -> None:
    tools, _ = tools_for(RunState.SYNTHESIZING)
    reply = rpc(tools, "tools/call", {"name": "search_evidence", "arguments": {"query": "x"}})
    assert reply["error"]["code"] == -32602


def test_array_arguments_are_checked() -> None:
    tools, _ = tools_for(RunState.RESEARCHING)
    bad = call(
        tools,
        "get_numeric_facts",
        {"instrument_id": "synthetic-issuer.eq", "concepts": ["revenue", 3]},
    )
    assert body(bad)["error_code"] == "INVALID_REQUEST"
    good = call(
        tools,
        "get_numeric_facts",
        {"instrument_id": "synthetic-issuer.eq", "concepts": ["revenue"]},
    )
    assert good["isError"] is False


# --- submissions ---------------------------------------------------------------------------


def test_first_submission_wins_and_is_never_validated_for_the_model() -> None:
    tools, sink = tools_for(RunState.SYNTHESIZING)
    first = call(tools, "submit_thesis", {"stance": "nonsense"})
    second = call(tools, "submit_thesis", {"stance": "watch"})
    assert first["isError"] is False
    assert "recorded" in first["content"][0]["text"]
    assert second["isError"] is True
    assert sink.payload == {"stance": "nonsense"}
    assert sink.attempts == 2


# --- HTTP transport ------------------------------------------------------------------------


@pytest.fixture
def server() -> Iterator[McpToolServer]:
    tools, _ = tools_for(RunState.RESEARCHING)
    front = McpToolServer(tools, token="mcp-token-123", host="127.0.0.1", port=0)
    front.start()
    yield front
    front.stop()


def post(server: McpToolServer, message: dict[str, Any], token: str = "mcp-token-123") -> Any:
    request = urllib.request.Request(
        server.url,
        data=json.dumps(message).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        text = response.read().decode()
        return response.status, (json.loads(text) if text else None)


def test_http_round_trip(server: McpToolServer) -> None:
    status, reply = post(server, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert status == 200
    assert len(reply["result"]["tools"]) == 9
    status, reply = post(server, {"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert (status, reply) == (202, None)


def test_http_requires_the_token(server: McpToolServer) -> None:
    with pytest.raises(urllib.error.HTTPError) as raised:
        post(server, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, token="wrong")
    assert raised.value.code == 401


def test_http_get_is_not_allowed(server: McpToolServer) -> None:
    request = urllib.request.Request(
        server.url, method="GET", headers={"Authorization": "Bearer mcp-token-123"}
    )
    with pytest.raises(urllib.error.HTTPError) as raised:
        urllib.request.urlopen(request, timeout=5)
    assert raised.value.code == 405


# --- candidates ----------------------------------------------------------------------------


def fixture_payload(name: str, stage: RunState) -> dict[str, Any]:
    payload = json.loads((FIXTURES / f"{name}.json").read_text())[stage.value]["payload"]
    return json.loads(json.dumps(payload).replace("${RUN}", "run.0001"))  # type: ignore[no-any-return]


@pytest.mark.parametrize(
    ("stage", "kind"),
    [
        (RunState.RESEARCHING, ResearchCandidate),
        (RunState.CRITIQUING, CritiqueCandidate),
        (RunState.SYNTHESIZING, ThesisCandidate),
    ],
)
def test_fixture_payloads_parse(stage: RunState, kind: type) -> None:
    assert isinstance(parse_candidate(stage, fixture_payload("completion", stage)), kind)


def test_malformed_candidates_are_rejected() -> None:
    with pytest.raises(ValidationError):
        parse_candidate(RunState.SYNTHESIZING, {"stance": "nonsense", "assertions": []})
    research = fixture_payload("completion", RunState.RESEARCHING)
    research["claims"][0]["key"] = "Bad Key!"
    with pytest.raises(ValidationError):
        parse_candidate(RunState.RESEARCHING, research)
    research = fixture_payload("completion", RunState.RESEARCHING)
    research["claims"][0]["epistemic_status"] = "hypothesized"
    with pytest.raises(ValidationError):
        parse_candidate(RunState.RESEARCHING, research)
    duplicated = fixture_payload("completion", RunState.RESEARCHING)
    duplicated["claims"][1]["key"] = "c1"
    with pytest.raises(ValidationError):
        parse_candidate(RunState.RESEARCHING, duplicated)


def test_numbers_are_strings_in_the_schema() -> None:
    schema = json.dumps(submit_schema(RunState.RESEARCHING))
    assert "$ref" not in schema
    assert '"value": {"type": "string"' in schema
