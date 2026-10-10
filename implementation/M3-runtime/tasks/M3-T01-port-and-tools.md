# M3-T01 — Runtime port, fake runtime and typed tools

| Field | Value |
|---|---|
| Status | TODO |
| Depends on | G2, M2-T05, M2-T06 |
| Phase constitution | [../CONSTITUTION.md](../CONSTITUTION.md) (inherits [global](../../CONSTITUTION.md)) |
| Plan source | plan §9 M3-T01 card, §3.2 (`RuntimeContext`, `StageResult`), §3.5 rule 10, §3.8; A5, A8 |
| Journal | `tasks/M3-T01-port-and-tools.journal.md` |

## 0. Context to load

Load these and nothing else:
- `implementation/CONSTITUTION.md`
- `implementation/M3-runtime/CONSTITUTION.md`, articles 1–3, 10 and 11
- [../PLAN.md](../PLAN.md), the architecture slice and open question 1
- `src/episalpha/contracts/research.py:281-382` (`Usage`, `StageResult`, `RunRecord`,
  `RuntimeContext`)
- `src/episalpha/evidence/snapshots.py:161-253` (`SnapshotView`: `document`, `span`, `text`,
  `search`, `missing_sources`, `has_essential_evidence`, `build_view`)
- `src/episalpha/research/derivations.py` (`recompute`, `REGISTRY`, from M1-T05)
- `src/episalpha/connectors/xbrl.py` (`XbrlFact`, from M2-T05)
- `src/episalpha/settings.py:263-308` (`Limits`)
- `src/episalpha/observability.py` (`event`, `timed`, `bind`)
- `config/runtime.lock.json`, the `hermes.custom_tool_injection_finding` field

> Typed tools reach Hermes as an **external MCP server**, not as in-process callables. The first
> task here is to prove that path with a minimal MCP server and one read-only tool, before any
> EpisAlpha tool surface is designed around it. (A5)

> Tool handlers obtain cutoff and snapshot from immutable run context. Agent-supplied dates
> cannot expand access. (plan §3.5 rule 10)

## 1. Plan

- **Goal:** a host-side runtime port, a deterministic fake, and seven typed read-only tools.
  All are bound to a frozen snapshot, and the MCP path has been proven able to carry them.
- **Files:**
  - `src/episalpha/runtime/port.py`
  - `src/episalpha/runtime/fake.py`
  - `src/episalpha/runtime/tools.py`
  - Focused test: `tests/runtime/test_tools.py`
- **Produces:**
  - `class ResearchRuntimePort(Protocol)`, with
    `def run_stage(self, stage: RunState, context: RuntimeContext) -> StageResult` and
    `def cancel(self) -> None`.
  - `class FakeRuntime`. It is deterministic and returns scripted `StageResult`s from fixtures.
    Every payload is labelled `{"fixture": true, "source": "<fixture path>"}`. It can simulate:
    completion, abstention, invalid references, provider failure, timeout, cancellation and
    partial output.
  - `class ToolHost(view: SnapshotView, context: RuntimeContext, limits: Limits)`, with one
    method per tool. Each returns a `ToolResult(Contract)` holding `ok`, `payload`,
    `error_code`, `result_hash` and `bytes`.

    | Tool | Input | Output |
    |---|---|---|
    | `resolve_instrument` | ticker | instrument ID within the snapshot, or `NO_DATA` |
    | `search_evidence` | query, limit ≤ `max_evidence_search_hits` | span IDs, quotes and document IDs |
    | `get_evidence_span` | span ID | the exact quote and locator; an outside-snapshot ID gives `NOT_AUTHORIZED` |
    | `get_market_context` | instrument ID | snapshot price context, with `adjustment_basis` always present; no multi-day return from unadjusted data (A6) |
    | `get_support_and_contradictions` | claim or hypothesis ID | relations within the snapshot and validated current-run records only |
    | `get_numeric_facts` (A8) | instrument ID, concepts | `NumericFact`s from the snapshot's eligible XBRL or reported claims |
    | `compute_derivation` (A8) | method, method_version, input claim IDs | `{value, unit, method, method_version}` computed host-side through `recompute` |

- **Limits:**
  - Tool calls are counted against `context.remaining_tool_calls`; when exhausted the result is
    `BUDGET_EXCEEDED`.
  - A result larger than `max_tool_result_bytes` gives `BUDGET_EXCEEDED`. It is never silently
    truncated.
- **Out of scope:**
  - The MCP server production wiring and the Hermes config (M3-T03).
  - The relay (M3-T02).
  - The runner (M4-T01).
- **Do not:**
  - Accept a cutoff, path, URL or SQL argument.
  - Read the SQLite DB from tools. Tools read the `SnapshotView` only.
  - Import Hermes here.

## 2. Verify (before building)

- [ ] **MCP path proof (A5), disposable.**
  - Write `scripts/probe_mcp.py`. It is a minimal MCP stdio server exposing one read-only tool
    (`echo_span`), first with the stdlib JSON-RPC.
  - Configure pinned Hermes, through its Docker image or the editable clone at `c1488ac`, with
    `mcp.json`.
  - Allowlist it with `create_custom_toolset('episalpha', tools=['mcp_echo_span'])` and
    `enabled_toolsets=['episalpha']`.
  - Run one agent turn on the active route. That is one or two requests and needs owner
    approval.
  - Journal: the effective tool list Hermes reports, the tool call trace, and whether `mcp_`
    prefixing held.
  - **If the proof fails or needs the `mcp` package:** stop. Record BLOCKED with the evidence
    and ask the owner. Do not design the tool surface around an unproven path.
  - If the proof itself becomes a multi-file effort, split it into its own task card
    (`M3-T01a`) and update `STATUS.md`.
- [ ] The interfaces exist:
      `grep -n "class SnapshotView\|def search\|def span\|class RuntimeContext\|def recompute" src/episalpha -r`.
- [ ] Baseline: the four checks and `diagnose.py` are green.
- [ ] **Red first.** Write `tests/runtime/test_tools.py` so it fails before the build. Cover:
  - Each tool's happy path on the synthetic snapshot.
  - An outside-snapshot span or claim gives `NOT_AUTHORIZED`.
  - An agent-supplied cutoff argument is impossible: the signature has no such parameter, and a
    test asserts that through `inspect`.
  - The search hit cap holds.
  - An oversize result gives `BUDGET_EXCEEDED`.
  - The tool-call budget runs out.
  - `result_hash` is stable.
  - `compute_derivation` equals `recompute`, and an unknown method gives a typed error.
  - `FakeRuntime` payloads carry the `fixture` label.
  - A `tool.call` event is emitted per call, with no payload text.

## 3. Build

1. Write the `port.py` Protocol and the `ToolResult` contract.
2. Write the `tools.py` `ToolHost`, wrapping each method in `timed(EventName.TOOL_CALL, tool=...)`.
3. Write the `fake.py` scripted runtime, with fixtures under `tests/fixtures/runtime/`.

## 4. Test

```bash
uv run pytest -q tests/runtime/test_tools.py
uv run ruff check . && uv run ruff format --check . && uv run mypy src/episalpha && uv run pytest -q -m "not live"
```

Acceptance:
- [ ] Every tool is bound to the snapshot and cutoff, enforces limits, returns typed errors, and
      records result hashes.
- [ ] Arbitrary SQL, URLs, filesystem paths or broader cutoffs cannot expand access.
- [ ] Fake output includes fixture provenance.
- [ ] The MCP path proof is recorded in the journal with real output, or the task is BLOCKED.

## 5. Diagnose

- [ ] `diagnose.py`: no regression; the new `tests/runtime` directory appears.
- [ ] Sample `tool.call` lines are in the journal.
- [ ] The MCP proof trace is summarized in the journal, together with the requests spent
      against the daily cap.

## 6. Stop and hand off

- **BLOCKED if:**
  - the MCP proof fails;
  - a new dependency is needed without approval;
  - `SnapshotView` lacks something a tool requires. Report it; do not widen the view silently.
- **Record:** M3 `PROGRESS.md`, `STATUS.md`, and the journal.
- **Next:** M3-T02.
