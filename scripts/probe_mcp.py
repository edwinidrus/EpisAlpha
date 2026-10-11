#!/usr/bin/env python3
"""Disposable MCP path proof for M3-T01 (amendment A5).

A minimal MCP server over stdio, written with the standard library only: newline-delimited
JSON-RPC 2.0, the legacy ``initialize`` handshake, ``tools/list`` and ``tools/call``. It exposes
one read-only tool, ``echo_span``, that returns a fixed synthetic quotation.

Pinned Hermes launches it as an ``mcp_servers`` stdio entry; the driver in the M3-T01 journal
shows the effective tool list, the tool-call trace and the name prefixing. If ``PROBE_LOG`` is
set, every request method is appended there, so the trace is observable without Hermes logs.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

HANDSHAKE_VERSIONS = ("2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25")
SPANS = {"synthetic-span.revenue": "Fourth quarter revenue was EUR 412.0 million."}

ECHO_SPAN = {
    "name": "echo_span",
    "description": "Return the exact stored quotation for one evidence span ID (read-only).",
    "inputSchema": {
        "type": "object",
        "properties": {"span_id": {"type": "string", "description": "An evidence span ID."}},
        "required": ["span_id"],
        "additionalProperties": False,
    },
}


def handle(message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    params = message.get("params") or {}
    if "id" not in message:  # a notification, e.g. notifications/initialized
        return None
    if method == "initialize":
        offered = params.get("protocolVersion")
        version = offered if offered in HANDSHAKE_VERSIONS else HANDSHAKE_VERSIONS[-1]
        result: dict[str, Any] = {
            "protocolVersion": version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "episalpha-probe", "version": "0"},
        }
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": [ECHO_SPAN]}
    elif method == "tools/call" and params.get("name") == "echo_span":
        span_id = (params.get("arguments") or {}).get("span_id")
        quote = SPANS.get(str(span_id))
        text = json.dumps({"span_id": span_id, "quote": quote} if quote else {"error": "NO_DATA"})
        result = {"content": [{"type": "text", "text": text}], "isError": quote is None}
    else:
        return {
            "jsonrpc": "2.0",
            "id": message["id"],
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }
    return {"jsonrpc": "2.0", "id": message["id"], "result": result}


def main() -> None:
    log = os.environ.get("PROBE_LOG")
    for line in sys.stdin:
        if not line.strip():
            continue
        message = json.loads(line)
        if log:
            with open(log, "a", encoding="utf-8") as handle_:
                handle_.write(
                    json.dumps(
                        {
                            "method": message.get("method"),
                            "id": message.get("id"),
                            "params": message.get("params"),
                        }
                    )
                    + "\n"
                )
        reply = handle(message)
        if reply is not None:
            sys.stdout.write(json.dumps(reply) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
