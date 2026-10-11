"""The host's MCP tool server for one research stage (plan M3; amendments A5, A13).

Hermes reaches EpisAlpha's typed tools as an external MCP server. The tools need the frozen
snapshot, which only the host has, so this server runs on the host and the worker connects to
it over MCP's Streamable HTTP transport (``url`` + ``Authorization`` header in the worker's
``mcp_servers`` config). It is written with the standard library and implements only what
Hermes' client was observed to use (M3-T01 journal): the legacy ``initialize`` handshake,
``notifications/initialized``, ``ping``, ``tools/list`` and ``tools/call``, answered as plain
JSON. Server-initiated streams (``GET``) are not offered (405).

Each stage gets its own tool list. The stage's ``submit_<stage>`` tool records the first
submission's raw arguments and tells the model to stop; it deliberately does not validate
them for the model, because a validate-and-retry loop would be an unbudgeted repair. The host
parses the submission after the stage (``candidates.parse_candidate``).
"""

from __future__ import annotations

import hmac
import json
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from episalpha.contracts.research import RunState
from episalpha.observability import SpanKind, TraceHandle, annotate, restore, span
from episalpha.runtime.candidates import SUBMIT_TOOLS, submit_schema
from episalpha.runtime.port import ToolResult
from episalpha.runtime.tools import ToolHost

HANDSHAKE_VERSIONS = ("2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25")
MAX_MESSAGE_BYTES = 262_144

_STRING: dict[str, Any] = {"type": "string"}
_STRINGS: dict[str, Any] = {"type": "array", "items": {"type": "string"}}


def _object(description: str, **properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "description": description,
        "properties": properties,
        "required": sorted(properties),
        "additionalProperties": False,
    }


READ_TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "resolve_instrument": _object(
        "Instrument ID in this snapshot for a ticker valid at the research cutoff.",
        ticker=_STRING,
    ),
    "search_evidence": _object(
        "Keyword search over this snapshot's evidence spans: spans containing more of the "
        "query's words rank first. Returns span IDs and exact quotes.",
        query=_STRING,
        limit={"type": "integer", "minimum": 1},
    ),
    "get_evidence_span": _object(
        "The exact quote, locator and document of one span ID.", span_id=_STRING
    ),
    "get_market_context": _object(
        "Frozen price context for an instrument, with its adjustment basis.",
        instrument_id=_STRING,
    ),
    "get_support_and_contradictions": _object(
        "Recorded SUPPORTS/CONTRADICTS links for a claim or a validated hypothesis.",
        record_id=_STRING,
    ),
    "get_numeric_facts": _object(
        "Reported numeric facts for an instrument; concepts filters by metric (empty = all).",
        instrument_id=_STRING,
        concepts=_STRINGS,
    ),
    "compute_derivation": _object(
        "Compute a registered derivation host-side from input claim IDs. Never compute "
        "numbers yourself; cite this result as a derived claim.",
        method=_STRING,
        method_version=_STRING,
        input_claim_ids=_STRINGS,
    ),
    "propose_skill": _object(
        "Propose a reusable research procedure for offline review. Data only; it changes "
        "nothing in this run. At most 2 per run.",
        title=_STRING,
        when_to_use=_STRING,
        procedure_steps=_STRINGS,
        rationale=_STRING,
        evidence_span_ids=_STRINGS,
    ),
}

_READ = (
    "resolve_instrument",
    "search_evidence",
    "get_evidence_span",
    "get_market_context",
    "get_support_and_contradictions",
    "get_numeric_facts",
    "compute_derivation",
)
STAGE_READ_TOOLS: dict[RunState, tuple[str, ...]] = {
    RunState.RESEARCHING: (*_READ, "propose_skill"),
    RunState.CRITIQUING: _READ,
    RunState.SYNTHESIZING: (
        "get_evidence_span",
        "get_support_and_contradictions",
        "compute_derivation",
    ),
}


@dataclass
class SubmissionSink:
    """Holds a stage's first submission, exactly as sent."""

    stage: RunState
    payload: dict[str, Any] | None = None
    attempts: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], tuple[str, bool]]
    """Takes validated arguments; returns the text content and whether it is an error."""


def _type_ok(value: Any, schema: dict[str, Any]) -> bool:
    kind = schema.get("type")
    if kind == "string":
        return isinstance(value, str)
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "array":
        return isinstance(value, list) and all(_type_ok(item, schema["items"]) for item in value)
    return False


def _arguments_error(schema: dict[str, Any], arguments: Any) -> str | None:
    if not isinstance(arguments, dict):
        return "arguments must be an object"
    properties: dict[str, Any] = schema["properties"]
    unknown = sorted(set(arguments) - set(properties))
    if unknown:
        return f"unknown arguments {unknown}"
    missing = sorted(set(schema["required"]) - set(arguments))
    if missing:
        return f"missing arguments {missing}"
    for name, value in arguments.items():
        if not _type_ok(value, properties[name]):
            return f"argument {name!r} must be {properties[name]['type']}"
    return None


def _tool_text(result: ToolResult) -> tuple[str, bool]:
    text = json.dumps(
        {
            "ok": result.ok,
            "payload": result.payload,
            "error_code": result.error_code.value if result.error_code else None,
        }
    )
    return text, not result.ok


def _invalid(message: str) -> tuple[str, bool]:
    return json.dumps(
        {"ok": False, "payload": {"error": message}, "error_code": "INVALID_REQUEST"}
    ), True


def stage_tools(host: ToolHost, stage: RunState, sink: SubmissionSink) -> list[ToolSpec]:
    """The tools one stage may see: its read tools plus its submit tool."""
    specs: list[ToolSpec] = []
    for name in STAGE_READ_TOOLS[stage]:
        schema = READ_TOOL_SCHEMAS[name]
        method = getattr(host, name)

        def handler(
            arguments: dict[str, Any],
            method: Callable[..., ToolResult] = method,
            schema: dict[str, Any] = schema,
        ) -> tuple[str, bool]:
            error = _arguments_error(schema, arguments)
            if error is not None:
                return _invalid(error)
            return _tool_text(method(**arguments))

        specs.append(ToolSpec(name, str(schema["description"]), schema, handler))

    submit_name = SUBMIT_TOOLS[stage]

    def submit(arguments: dict[str, Any]) -> tuple[str, bool]:
        with sink.lock:
            sink.attempts += 1
            first = sink.payload is None
            if first:
                sink.payload = arguments
        with span(
            f"tool.{submit_name}",
            SpanKind.TOOL,
            **{"tool.name": submit_name, "tool.parameters": json.dumps(arguments)},
        ) as current:
            annotate(current, **{"episalpha.accepted": first, "episalpha.attempt": sink.attempts})
        if not first:
            return "Already submitted; only the first submission counts. Stop now.", True
        return "Submission recorded. Your stage is complete: stop now.", False

    submit_spec = submit_schema(stage)
    specs.append(
        ToolSpec(
            submit_name,
            "Submit this stage's final structured output. Call it exactly once, last.",
            submit_spec,
            submit,
        )
    )
    return specs


def _reply(message_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "result": result}


def _rpc_error(message_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "error": {"code": code, "message": message}}


def handle_rpc(tools: Sequence[ToolSpec], message: Any) -> dict[str, Any] | None:
    """Answer one JSON-RPC message; ``None`` for a notification."""
    if not isinstance(message, dict) or "method" not in message:
        return _rpc_error(None, -32600, "invalid request")
    if "id" not in message:
        return None
    message_id = message["id"]
    method = message["method"]
    params = message.get("params") or {}
    if method == "initialize":
        offered = params.get("protocolVersion")
        version = offered if offered in HANDSHAKE_VERSIONS else HANDSHAKE_VERSIONS[-1]
        return _reply(
            message_id,
            {
                "protocolVersion": version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "episalpha", "version": "1"},
            },
        )
    if method == "ping":
        return _reply(message_id, {})
    if method == "tools/list":
        return _reply(
            message_id,
            {
                "tools": [
                    {"name": t.name, "description": t.description, "inputSchema": t.input_schema}
                    for t in tools
                ]
            },
        )
    if method == "tools/call":
        by_name = {tool.name: tool for tool in tools}
        tool = by_name.get(str(params.get("name")))
        if tool is None:
            return _rpc_error(message_id, -32602, f"unknown tool {params.get('name')!r}")
        text, is_error = tool.handler(params.get("arguments") or {})
        return _reply(
            message_id, {"content": [{"type": "text", "text": text}], "isError": is_error}
        )
    return _rpc_error(message_id, -32601, f"method not found: {method}")


class McpToolServer:
    """Streamable-HTTP MCP endpoint at ``/mcp`` for one stage. Bearer token required."""

    def __init__(
        self,
        tools: Sequence[ToolSpec],
        *,
        token: str,
        host: str,
        port: int,
        trace: TraceHandle | None = None,
    ) -> None:
        self.tools = list(tools)
        lock = threading.Lock()
        tool_list = self.tools

        class Handler(BaseHTTPRequestHandler):
            def _authorized(self) -> bool:
                presented = self.headers.get("Authorization", "").removeprefix("Bearer ").strip()
                return hmac.compare_digest(presented.encode(), token.encode())

            def do_POST(self) -> None:  # noqa: N802 - http.server API
                if not self._authorized():
                    self._send(401, None)
                    return
                length = int(self.headers.get("Content-Length") or 0)
                if length > MAX_MESSAGE_BYTES:
                    self._send(413, None)
                    return
                try:
                    message = json.loads(self.rfile.read(length))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    self._send(400, _rpc_error(None, -32700, "parse error"))
                    return
                with lock, restore(trace):
                    if isinstance(message, list):
                        replies = [handle_rpc(tool_list, item) for item in message]
                        answer: Any = [reply for reply in replies if reply is not None] or None
                    else:
                        answer = handle_rpc(tool_list, message)
                self._send(202 if answer is None else 200, answer)

            def do_GET(self) -> None:  # noqa: N802
                self._send(405, None)

            def do_DELETE(self) -> None:  # noqa: N802
                self._send(405, None)

            def _send(self, status: int, payload: Any) -> None:
                body = b"" if payload is None else json.dumps(payload).encode()
                self.send_response(status)
                if payload is not None:
                    self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:  # noqa: A002
                return None

        self._server = ThreadingHTTPServer((host, port), Handler)
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        return int(self._server.server_address[1])

    @property
    def url(self) -> str:
        host = str(self._server.server_address[0])
        return f"http://{host}:{self.port}/mcp"

    def start(self) -> None:
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
