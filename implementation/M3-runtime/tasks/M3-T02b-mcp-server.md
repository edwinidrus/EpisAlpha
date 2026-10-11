# M3-T02b — MCP tool server and stage candidate schemas

| Field | Value |
|---|---|
| Status | DONE |
| Depends on | M3-T02 |
| Phase constitution | [../CONSTITUTION.md](../CONSTITUTION.md) (inherits [global](../../CONSTITUTION.md)) |
| Plan source | plan §9 M3-T01/M3-T03 cards, §3.6 stages 3–7; A3, A5, A13 |
| Journal | `tasks/M3-T02b-mcp-server.journal.md` |
| Origin | Split out of M3-T03 on 2026-10-11 (global article 19): M3-T03 needed five implementation files. |

## 0. Context to load

- `implementation/CONSTITUTION.md`; `implementation/M3-runtime/CONSTITUTION.md`, articles 1–3, 5, 7, 11
- The M3-T01 journal (MCP proof: Hermes' client does the legacy `initialize` handshake) and the
  M3-T02 journal (Hermes request shapes)
- `src/episalpha/runtime/tools.py` (`ToolHost`), `src/episalpha/contracts/research.py`
  (`ThesisSection`, `ResearchStance`), `src/episalpha/contracts/knowledge.py`
  (`EpistemicStatus`, `NumericFact`)

**Why HTTP.** Hermes cannot be imported into the application venv (it exact-pins its
dependencies), and the worker runs in its own environment or container, where the snapshot does
not exist. The typed tools therefore stay on the host, behind a token-protected MCP server
using the Streamable HTTP transport, which Hermes' MCP client supports (`url` + `headers`).

## 1. Plan

- **Goal:** a stdlib MCP server that exposes one stage's allowed `ToolHost` tools plus that
  stage's `submit_<stage>` tool, and host-side candidate schemas that parse what a stage submits.
- **Files:**
  - `src/episalpha/runtime/mcp_server.py`: `handle_rpc` (pure JSON-RPC), `McpToolServer`
    (stdlib HTTP, bearer token, JSON responses, GET/DELETE answered 405), `stage_tools(host,
    stage, sink)`.
  - `src/episalpha/runtime/candidates.py`: `ResearchCandidate`, `CritiqueCandidate`,
    `ThesisCandidate`, `parse_candidate(stage, payload)`, and inlined JSON schemas for the
    submit tools.
  - Focused test: `tests/runtime/test_mcp_server.py`.
- **Rules:**
  - The researcher sees the read tools plus `propose_skill` and `submit_research`. The critic
    sees the read tools plus `submit_critique`. The synthesizer sees `get_evidence_span`,
    `get_support_and_contradictions`, `compute_derivation` and `submit_thesis`.
  - The submit tool records the **first** submission's raw arguments and answers "recorded,
    stop". It never validates them for the model: that would be an unbudgeted repair loop.
    The host parses after the stage (M3-T03); malformed means `INVALID_OUTPUT`.
  - Arguments of the wrong type give a tool error (`INVALID_REQUEST`), never an exception.
  - Candidate claim keys match `^[a-z][a-z0-9_-]{0,15}$`; the host assigns canonical IDs
    `<run_id>.<key>`.
- **Do not:** add the `mcp` package to EpisAlpha; accept a request without the run token; bind
  to a non-loopback address from this module (M3-T04 chooses the bind address).

## 2. Verify

- [ ] Baseline four checks green. Red first.
- [ ] Pinned Hermes registers the HTTP server and lists the stage's tools, with no model call.

## 4. Test

```bash
uv run pytest -q tests/runtime/test_mcp_server.py
uv run ruff check . && uv run ruff format --check . && uv run mypy src/episalpha && uv run pytest -q -m "not live"
```

Acceptance: the JSON-RPC subset is covered; the token is enforced; each stage exposes exactly
its tools; the first submission wins; schemas parse the fake fixtures; Hermes registers the
server.

## 6. Stop and hand off

- **Record:** M3 `PROGRESS.md`, `STATUS.md`, and the journal.
- **Next:** M3-T03.
