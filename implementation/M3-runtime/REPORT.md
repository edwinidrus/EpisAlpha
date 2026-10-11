# M3 phase report: bounded Hermes runtime

**Gate G3: PASSED on 2026-10-11.** Real research stages ran on pinned Hermes 0.21.3 against the
OpenRouter route: once with a local worker, once inside the hardened container. The worker
proposes; the host validates, counts and refuses. One owner action is open: the Docker engine is
rootful and hardened only (see below).

## What M3 delivers

| Task | Status | What exists now |
|---|---|---|
| M3-T01 | DONE | `ResearchRuntimePort`, `FakeRuntime` (7 labelled scenarios), `ToolHost` with 8 snapshot-bound tools; MCP path proven on pinned Hermes |
| M3-T02 | DONE | `ModelRelay`: the only holder of the key, one route, field allowlist, run-global budget, bounded retries, SSE replay for the streaming worker |
| M3-T02b | DONE (split from M3-T03) | Host MCP tool server over Streamable HTTP; strict stage candidate schemas |
| M3-T03 | DONE | `HermesRuntime` + `worker/hermes_stage.py` + baseline harness; three stages live |
| M3-T04 | DONE | Hardened container worker; boundary proven; real-provider run through the container |

## How a stage runs

```text
host: HermesRuntime ── starts ──▶ MCP tool server (stage's tools + submit_<stage>)
  │                               relay (StagePolicy: N requests, last one forces submit)
  └─ docker run worker ─────────▶ [internal net, no host address, no DNS]
       Hermes 0.21.3 ── forwarder:8080 ──▶ relay (key lives here) ──▶ OpenRouter
                     ── forwarder:8081 ──▶ MCP tool server (snapshot-bound)
  submit_<stage> args ──▶ host parses (candidates.py) ── malformed = invalid_output
```

## What the evidence shows

- **MCP works with a stdlib server.** Hermes' MCP client performs the legacy `initialize`
  handshake. Tools are named `mcp__<server>__<tool>` (double underscores; the M0-T03 note was
  wrong).
- **Three Hermes defaults had to be switched off.** These were found and fixed, not assumed:
  - **Tool search:** with the default `tools.tool_search.enabled: auto`, the model only saw
    `tool_search`/`tool_describe`/`tool_call` meta-tools. It spent 3 requests discovering one
    tool and never called it.
  - **Summary request:** when the iteration budget runs out, Hermes makes one hidden extra
    "summary" request. The worker disables it.
  - **Learning defaults:** every learning key exists at the pin and defaults to **on**: memory,
    user profile, background review, curator, plus `write_approval: false`. The worker turns
    them all off.
- **This route does not honour `tool_choice: "required"`.** It returned a pseudo tool call as
  text. Named forcing does work (M0-T04). Each stage now explores with `auto`, and the relay
  forces the stage's submit tool on its last request. Caps are 4 (researcher), 2 (critic) and
  1 (synthesizer), leaving 1 of 8 for M4's repair.
- **Pinned Hermes streams.** The relay calls the provider without streaming and replays the
  result as SSE.
- **Retrieval mattered.** In the first live run the critic wrongly reported "no demand evidence"
  because `search_evidence` matched whole phrases. Keyword scoring fixed it, and the next run
  cited the right spans.
- **The host refuses malformed output.** Live run 1's synthesizer submitted an assertion with no
  references. It was rejected as `invalid_output`, never quietly accepted.
- **The container boundary holds** (probe inside the real worker): no repository, `.env`,
  database, `/mnt/c`, host home or Docker socket; no DNS or internet; spec, root filesystem and
  skills mount not writable; the fork bomb and tmpfs fill are contained; a planted symlink is not
  followed; only the relay (via the forwarder) is reachable. Cancel and timeout each stop the
  container in **2.57 s**.
- **A network trap found and closed.** A plain `--internal` Docker network still lets
  containers reach every host service bound to `0.0.0.0` through the bridge address. This host
  has two (ports 8000 and 8080). The worker network now uses
  `com.docker.network.bridge.inhibit_ipv4=true`, so the host has no address on it.

## Live runs (synthetic snapshot; not evidence about any real company)

| Run | Worker | Requests | Result | Trace |
|---|---|---:|---|---|
| 2026-10-11 06:13 | local venv | 7 | synthesizer `invalid_output` (no references) | `433e7715…` |
| 2026-10-11 06:17 | local venv | 6 | 3/3 stages completed, valid citations | `279e56da…` |
| 2026-10-11 06:29 | **container** | 6 | 3/3 stages completed, valid citations | `f8c7b412…` |

Every call was served by Nvidia. The relay's request count equalled the sum of stage requests,
so there were no hidden calls, and no Hermes skill, memory or conversation persisted. Free-tier
spend for the whole unattended session so far: **28 of the 40 approved requests**, including
probes and one failed attempt.

## Numbers

| Measure | Before M3 | After |
|---|---:|---:|
| Default suite | 399 | 504 |
| `tests/runtime` | 0 | 105 |
| Source files under strict mypy | 23 | 32 |
| New runtime dependencies | — | none (stdlib HTTP, MCP and forwarder) |

## Deviations (each recorded in its journal)

1. **M3-T03 was split** into M3-T02b and M3-T03 (global article 19).
2. **Hermes is never imported by the app.** The worker runs in Hermes' own environment, and the
   tools travel over MCP HTTP. This is a stronger quarantine than the planned
   `runtime/hermes.py` import.
3. **A minimal worker image** built from the pinned commit's `git archive` and `uv.lock`, not
   upstream's heavy image, which has no 0.21.3 tag.
4. **`container/` instead of `runtime/`**, and no `compose.yaml`: `sandbox.py` issues the docker
   commands itself, and tests pin them.
5. **Red-first slipped** for `hermes.py` and `sandbox.py`: code came before its offline tests.
   The tests were then written against the packs' lists.
6. **Two M3-T01 tests changed queries** (`"e"` to `"quarter demand"`) after the keyword-search
   change; their assertions are unchanged.

## Open items for the owner

- **Docker engine:** move the worker to rootless Docker or userns-remap (optionally gVisor). As
  it stands, a container escape lands as root in the WSL distro holding `.env` and `/mnt/c`.
- **The relay and MCP servers bind on docker0 (172.17.0.1).** Other containers on the default
  bridge can reach them, but per-run tokens gate both.
- **Hermes invokes `uv` inside the sandbox**, probably a lazy-dependency check. With no network
  nothing installs, but it is worth understanding.
- **The worker image is a local build.** Its content ID is the pin; a rebuild must record its
  new ID in `config/runtime.lock.json`.
