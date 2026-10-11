#!/usr/bin/env python3
"""Disposable integration probe for M0-T03, extended for the OpenRouter route in M0-T04.

Answers one question: what does the selected model route actually support, as opposed to what
its OpenAI-compatible surface advertises? Findings are recorded in
``docs/implementation/hermes_probe.md`` and pinned in ``config/runtime.lock.json``.

Run it with the credential exported, for example::

    set -a; source .env; set +a
    uv run python scripts/probe_hermes.py config/demo.toml

This probe deliberately makes real model calls. It is not part of the default test suite.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

# ponytail: stdlib urllib, not httpx. A throwaway probe does not justify pulling a runtime
# dependency forward from M3-T02, and urllib reports HTTP status and body well enough here.

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from episalpha.settings import ProviderRoute, load_settings  # noqa: E402

TIMEOUT_SECONDS = 120

# OpenRouter-specific: forbid routing to another provider. Sent only after a call shows the
# endpoint accepts the field; a rejection is recorded, not hidden (M0 constitution article 3).
NO_FALLBACKS: dict[str, Any] = {"provider": {"allow_fallbacks": False}}

SUBMIT_THESIS_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "submit_thesis",
        "description": "Submit the final structured thesis.",
        "parameters": {
            "type": "object",
            "properties": {
                "stance": {"type": "string", "enum": ["investigate", "watch", "abstain"]},
                "assertions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "section": {
                                "type": "string",
                                "enum": ["observation", "interpretation"],
                            },
                            "text": {"type": "string"},
                            "claim_ids": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["section", "text", "claim_ids"],
                    },
                },
            },
            "required": ["stance", "assertions"],
        },
    },
}

JSON_SCHEMA_FORMAT: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "thesis",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "stance": {"type": "string", "enum": ["investigate", "watch", "abstain"]},
                "assertion": {"type": "string"},
            },
            "required": ["stance", "assertion"],
            "additionalProperties": False,
        },
    },
}


def call(route: ProviderRoute, payload: dict[str, Any]) -> dict[str, Any]:
    """POST one chat completion. Raises on transport or HTTP error."""
    if route.endpoint_url is None or route.model_id is None:
        raise SystemExit("provider.endpoint_url and provider.model_id must be configured")
    credential = route.credential()
    headers = {"Content-Type": "application/json"}
    if credential is not None:
        headers["Authorization"] = f"Bearer {credential}"
    request = urllib.request.Request(  # noqa: S310 - endpoint comes from validated settings
        f"{route.endpoint_url.rstrip('/')}/chat/completions",
        data=json.dumps({"model": route.model_id, **payload}).encode(),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
        parsed: dict[str, Any] = json.load(response)
    return parsed


def probe_tool_call(route: ProviderRoute, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Does a forced tool call return arguments that parse against the declared schema?"""
    response = call(
        route,
        {
            **(extra or {}),
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Emit the final thesis for clearly synthetic test data using the "
                        "submit_thesis tool. stance must be watch."
                    ),
                }
            ],
            "tools": [SUBMIT_THESIS_TOOL],
            "tool_choice": {"type": "function", "function": {"name": "submit_thesis"}},
            "max_tokens": 2000,
        },
    )
    choice = response["choices"][0]
    tool_calls = choice["message"].get("tool_calls") or []
    result: dict[str, Any] = {
        "finish_reason": choice.get("finish_reason"),
        "forced_tool_choice_honored": bool(tool_calls),
        "arguments_parse_as_json": False,
        "usage_reported": response.get("usage") is not None,
        "usage": response.get("usage"),
        "served_by": response.get("provider"),
    }
    if tool_calls:
        try:
            arguments = json.loads(tool_calls[0]["function"]["arguments"])
        except json.JSONDecodeError:
            return result
        result["arguments_parse_as_json"] = True
        result["keys"] = sorted(arguments)
    return result


def probe_response_format(route: ProviderRoute) -> dict[str, Any]:
    """Is provider-side structured output honored, silently ignored, or rejected?"""
    try:
        response = call(
            route,
            {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Return stance=watch and one assertion about synthetic test data."
                        ),
                    }
                ],
                "response_format": JSON_SCHEMA_FORMAT,
                "max_tokens": 2000,
            },
        )
    except urllib.error.HTTPError as error:
        # A rejection is an observation, not a probe failure.
        return {
            "json_schema_honored": False,
            "rejected_status": error.code,
            "body_prefix": error.read()[:200].decode(errors="replace"),
        }
    content = response["choices"][0]["message"].get("content") or ""
    try:
        json.loads(content)
    except json.JSONDecodeError:
        honored = False
    else:
        honored = True
    return {"json_schema_honored": honored, "content_prefix": content[:120]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path, help="path to a settings TOML file")
    arguments = parser.parse_args()

    route = load_settings(arguments.config).provider
    print(f"endpoint : {route.endpoint_url}")
    print(f"model    : {route.model_id}")
    print(f"credential resolved: {route.credential() is not None}")

    try:
        tool_call = probe_tool_call(route, NO_FALLBACKS)
        tool_call["no_fallbacks_accepted"] = True
    except urllib.error.HTTPError as error:
        if not 400 <= error.code < 500 or error.code == 429:
            raise
        print(f"provider pin refused with HTTP {error.code}; retrying without it")
        tool_call = probe_tool_call(route)
        tool_call["no_fallbacks_accepted"] = False
        tool_call["no_fallbacks_rejected_status"] = error.code

    findings = {"tool_call": tool_call, "response_format": probe_response_format(route)}
    print(json.dumps(findings, indent=2))

    if not (tool_call["forced_tool_choice_honored"] and tool_call["arguments_parse_as_json"]):
        print(
            "BLOCKED: this route cannot deliver structured output via tool calls", file=sys.stderr
        )
        return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.HTTPError as error:
        # Retry-After on a 429 is evidence for the free-tier limit.
        retry_after = error.headers.get("Retry-After")
        body = error.read()[:400]
        print(f"HTTP {error.code} Retry-After={retry_after}: {body!r}", file=sys.stderr)
        raise SystemExit(1) from None
