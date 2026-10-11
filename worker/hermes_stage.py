#!/usr/bin/env python3
"""Run one EpisAlpha research stage inside pinned Hermes (plan M3-T03).

This file runs in **Hermes' own environment** (its venv or container), never in the EpisAlpha
application venv: Hermes exact-pins its dependencies. It uses only the standard library plus
Hermes, and it is the only code that imports Hermes, so Hermes' untyped surface never reaches
the type-checked application (M3 constitution article 9).

    <hermes-python> worker/hermes_stage.py <spec.json> <result.json>

The spec (written by ``episalpha.runtime.hermes``) names the relay, the host MCP tool server,
the prompts and the budgets. The worker:

1. writes a locked-down ``$HERMES_HOME/config.yaml``: memory, user profile, background review,
   curator and tool search off; skill writes need approval;
2. registers the host MCP server and allowlists exactly its tools;
3. refuses to run when the effective tool list differs from the allowlist;
4. runs one conversation and interrupts it as soon as the stage's submit tool returns, so the
   turn ends without a further model request; Hermes' extra iteration-exhausted "summary"
   request is disabled, because it would spend budget no one approved;
5. writes a small result JSON. The stage's output itself travels through the submit tool to the
   host, never through this file.

It never sees a provider key: ``api_key`` is the per-run relay token.
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any

CONFIG = """\
memory:
  memory_enabled: false
  user_profile_enabled: false
auxiliary:
  background_review:
    enabled: false
curator:
  enabled: false
skills:
  write_approval: true
tools:
  tool_search:
    enabled: "off"
"""


def home_report(home: str) -> dict[str, Any]:
    """What this stage left in HERMES_HOME: file list and persisted conversation rows."""
    files = sorted(
        os.path.relpath(os.path.join(root, name), home)
        for root, _, names in os.walk(home)
        for name in names
    )
    rows = None
    database = os.path.join(home, "state.db")
    if os.path.isfile(database):
        import sqlite3

        try:
            with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
                rows = sum(
                    int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                    for table in ("sessions", "messages")
                )
        except sqlite3.Error:
            rows = None
    return {"worker_home_files": files[:50], "worker_state_db_rows": rows}


def write_result(path: str, result: dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(result, handle, default=str)


def run(spec: dict[str, Any], result_path: str) -> int:
    home = os.environ.get("HERMES_HOME")
    if not home:
        write_result(result_path, {"error": "HERMES_HOME_MISSING"})
        return 2
    os.makedirs(home, exist_ok=True)
    with open(os.path.join(home, "config.yaml"), "w", encoding="utf-8") as handle:
        handle.write(CONFIG)

    from tools.mcp_tool_discovery import register_mcp_servers
    from toolsets import create_custom_toolset

    names = register_mcp_servers(
        {
            "episalpha": {
                "url": spec["mcp_url"],
                "headers": {"Authorization": f"Bearer {spec['mcp_token']}"},
            }
        }
    )
    create_custom_toolset("episalpha", "EpisAlpha typed tools", tools=list(names))

    from run_agent import AIAgent

    holder: dict[str, Any] = {"submitted": False}

    def on_tool_complete(*args: Any, **kwargs: Any) -> None:
        name = args[1] if len(args) > 1 else kwargs.get("name")
        if name == spec["submit_tool"] and not holder["submitted"]:
            holder["submitted"] = True
            holder["agent"].interrupt("stage submitted")

    overrides = {"tool_choice": "required"} if spec.get("force_tool_choice") else {}
    agent = AIAgent(
        base_url=spec["relay_url"],
        api_key=spec["relay_token"],
        model=spec["model"],
        enabled_toolsets=["episalpha"],
        max_iterations=int(spec["max_iterations"]),
        max_tokens=int(spec["max_tokens"]),
        session_id=spec["session_id"],
        quiet_mode=True,
        save_trajectories=False,
        skip_context_files=True,
        skip_memory=True,
        skip_background_review=True,
        load_soul_identity=False,
        request_overrides=overrides,
        tool_complete_callback=on_tool_complete,
    )
    holder["agent"] = agent
    # No hidden requests: when the iteration budget runs out, Hermes would make one extra
    # tool-less "summary" call. The stage fails visibly instead (no submission).
    agent._handle_max_iterations = lambda messages, count: ""

    effective = sorted(tool["function"]["name"] for tool in (agent.tools or []))
    base = {
        "effective_tools": effective,
        "registered_tools": sorted(names),
        "fallback_model": getattr(agent, "fallback_model", None),
    }
    if effective != sorted(spec["allowed_tools"]):
        write_result(result_path, {**base, "error": "TOOL_ALLOWLIST_MISMATCH"})
        return 3

    started = time.monotonic()
    outcome = agent.run_conversation(spec["user_prompt"], system_message=spec["system_prompt"])
    messages = outcome.get("messages", []) if isinstance(outcome, dict) else []
    tool_calls = [
        call["function"]["name"]
        for message in messages
        if message.get("role") == "assistant"
        for call in (message.get("tool_calls") or [])
    ]
    final = outcome.get("final_response") if isinstance(outcome, dict) else None
    write_result(
        result_path,
        {
            **base,
            "error": None,
            "submitted": holder["submitted"],
            "interrupted": bool(outcome.get("interrupted")) if isinstance(outcome, dict) else None,
            "api_calls": outcome.get("api_calls") if isinstance(outcome, dict) else None,
            "tool_calls": tool_calls,
            "final_response_prefix": str(final or "")[:300],
            "seconds": round(time.monotonic() - started, 2),
            **home_report(home),
        },
    )
    return 0


def main() -> int:
    spec_path, result_path = sys.argv[1], sys.argv[2]
    with open(spec_path, encoding="utf-8") as handle:
        spec = json.load(handle)
    try:
        return run(spec, result_path)
    except Exception as error:  # report, never hang: the host reads the result file
        write_result(result_path, {"error": f"WORKER_EXCEPTION: {type(error).__name__}"})
        return 1


if __name__ == "__main__":
    sys.exit(main())
