# M0 plan: foundation and integration feasibility

**Goal:** a runnable project, a verified research route, and a Diagnose layer that lets any later
session see what works and what does not.

**Plan source:** plan §6 (M0-T01..T03), amendments A1, A5, A9, A11.

## Tasks

| Task | Title | Status | Depends on | Pack |
|---|---|---|---|---|
| M0-T01 | Bootstrap owned application | DONE | — | — |
| M0-T02 | Resolve settings and record execution state | DONE | M0-T01 | — |
| M0-T02b | Source model expansion (A2) | DONE | M0-T02 | — |
| M0-T03 | Probe official Hermes and one model route | DONE (Hermes end-to-end unproven; carried to M3) | M0-T02 | — |
| M0-T04 | Research route moves to OpenRouter (A9) | DONE (verified live 2026-10-10) | M0-T03 | [pack](tasks/M0-T04-openrouter-route.md) |
| M0-T05 | Implementation diagnostics script (A11) | DONE | M0-T01 | [pack](tasks/M0-T05-diagnose-script.md) |
| M0-T06 | OpenTelemetry observability foundation (A11, A14) | DONE | M0-T02 | [pack](tasks/M0-T06-observability.md) |
| M0-T07 | Local Arize Phoenix diagnose service (A14) | DONE | M0-T06 | [pack](tasks/M0-T07-phoenix.md) |

Order: M0-T04 → M0-T05 → M0-T06 → M0-T07. T05, T06 and T07 do not depend on T04. If T04 is
blocked on a live call, they can proceed.

## Scope

- **In:**
  - Route switch: config, lock, probe evidence.
  - `scripts/diagnose.py`.
  - `src/episalpha/observability.py`, on OpenTelemetry, with a JSONL fallback exporter.
  - `observability/compose.yaml`, a local Phoenix on `127.0.0.1:6006`.
- **Out:**
  - The model relay (M3-T02).
  - Hermes runtime work (M3).
  - Instrumenting existing modules (M2-T06, then each later task).

## Known facts about the new route (from the OpenRouter `/api/v1/models` listing, 2026-10-10)

Unprobed. M0-T04 confirms or corrects every row.

| Property | `nvidia/nemotron-3-ultra-550b-a55b:free` |
|---|---|
| Endpoint | `https://openrouter.ai/api/v1` (`/chat/completions`) |
| Credential | `ENV:openrouter_api_key` (the model name is also in `.env` as `openrouter_model`) |
| Context window | 1,000,000 tokens |
| Max completion | 65,536 tokens |
| Listed parameters | `tools`, `tool_choice`, `reasoning`, `reasoning_effort`, `include_reasoning`, `seed`, `max_tokens`, `temperature`, `top_p` |
| `response_format` | **Not listed** for `:free`, although the paid variant lists it |
| Pricing | 0 / 0 |
| Free-tier limits | 20 requests/min; 50/day, or 1,000/day once at least $10 of credits has ever been purchased (OpenRouter blog, 2026; unprobed) |
| Data policy | Unconfirmed for `:free`; prompts may be logged by the provider |

**Budget consequence.** Settings allow 8 model requests per run, so 50 requests/day gives at
most **6 runs/day**. That suffices for M3 and M4. It does **not** suffice for the M6 campaign
(about 100 or more requests). The owner decides on credits or a multi-day campaign at M6.

## Open questions (owner)

1. Acknowledge the unconfirmed `:free` data-logging policy. The corpus is public SEC filings.
2. Approve the M0-T04 live calls (about 4 requests).
3. M0-T03's Hermes end-to-end turn is still unproven. That remains an M3-T01/M3-T03 item and is
   not re-opened here.
