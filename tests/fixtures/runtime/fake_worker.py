"""A stand-in for worker/hermes_stage.py in offline tests. Stdlib only; never a model call.

FAKE_WORKER_MODE selects the behaviour: submit_valid, submit_malformed, mismatch, no_submit,
sleep. FAKE_WORKER_PAYLOAD names a JSON file holding the submission for submit_valid.
"""

import json
import os
import sys
import time
import urllib.request

PREFIX = "mcp__episalpha__"


def rpc(spec, method, params=None, id_=1):
    message = {"jsonrpc": "2.0", "id": id_, "method": method, "params": params or {}}
    request = urllib.request.Request(
        spec["mcp_url"],
        data=json.dumps(message).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {spec['mcp_token']}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read())


def main():
    spec_path, result_path = sys.argv[1], sys.argv[2]
    spec = json.load(open(spec_path))
    mode = os.environ.get("FAKE_WORKER_MODE", "submit_valid")
    base = {"env_keys": sorted(os.environ), "spec_keys": sorted(spec), "error": None}
    if mode == "sleep":
        time.sleep(30)
    if mode == "mismatch":
        json.dump({**base, "error": "TOOL_ALLOWLIST_MISMATCH"}, open(result_path, "w"))
        return 3
    listed = rpc(spec, "tools/list")["result"]["tools"]
    base["effective_tools"] = sorted(PREFIX + tool["name"] for tool in listed)
    open(os.path.join(os.environ["HERMES_HOME"], "config.yaml"), "w").write("x: 1\n")
    if mode == "state_db":
        import sqlite3

        db = sqlite3.connect(os.path.join(os.environ["HERMES_HOME"], "state.db"))
        db.execute("CREATE TABLE sessions (id TEXT)")
        db.execute("CREATE TABLE messages (id TEXT)")
        db.execute("INSERT INTO sessions VALUES ('s1')")
        db.commit()
        db.close()
    if "search_evidence" in {tool["name"] for tool in listed}:
        rpc(
            spec,
            "tools/call",
            {"name": "search_evidence", "arguments": {"query": "demand", "limit": 2}},
        )
    submit = spec["submit_tool"].removeprefix(PREFIX)
    if mode == "submit_valid":
        payload = json.load(open(os.environ["FAKE_WORKER_PAYLOAD"]))
        rpc(spec, "tools/call", {"name": submit, "arguments": payload})
    elif mode == "submit_malformed":
        rpc(spec, "tools/call", {"name": submit, "arguments": {"stance": "nonsense"}})
    json.dump({**base, "submitted": mode.startswith("submit")}, open(result_path, "w"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
