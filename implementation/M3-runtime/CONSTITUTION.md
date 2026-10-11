# M3 constitution: bounded Hermes runtime

Inherits [../CONSTITUTION.md](../CONSTITUTION.md). The articles below add to it and never relax it.

1. **The worker proposes; the host disposes.**
   - Hermes returns *candidate* stage payloads.
   - Nothing it emits becomes canonical without host validation and host-assigned IDs.
2. **Tools never modify canonical or active state, and are snapshot-bound (A13).**
   - Every tool is read-only except `propose_skill`. That tool only appends a proposal to
     the run's own candidate set, as data; it never activates or edits a skill.
   - Every tool takes its cutoff and snapshot from the immutable `RuntimeContext`, never from
     arguments.
   - No tool accepts SQL, a URL, a filesystem path or a date that widens access.
   - Each result is size-capped (`max_tool_result_bytes`) and hashed.
3. **Arithmetic belongs to the host (A8).** `compute_derivation` runs the M1-T05 registry
   host-side. The model may request a computation; it never supplies the result.
4. **One route, fail closed.**
   - The relay forwards only to the configured `provider.endpoint_url` / `provider.model_id`.
   - An unknown model or path is rejected.
   - No provider fallback (OpenRouter `allow_fallbacks: false` if M0-T04 found it accepted).
   - The provider that served each call is recorded.
5. **Structured output comes from forced `tool_choice` (A3).**
   - The relay never sends `response_format`.
   - Arguments are parsed and validated host-side.
   - One bounded repair, no more.
6. **Budgets are global per run.**
   - Requests, retries, tool calls, output tokens and wall time come from `Settings.limits`.
   - Budgets are never reset by a new stage, a worker restart or a retry.
   - Free-tier route caps (20 requests/min; 50 or 1,000 requests/day) are respected. A 429 is a
     provider failure that counts toward the budget. It is never an abstention.
7. **Credentials live only in the trusted relay.**
   - The worker and container never see a provider key.
   - The worker authenticates to the relay with a per-run, short-lived token.
8. **Isolation is whole-worker.**
   - The Hermes worker runs in its container.
   - It mounts the frozen snapshot and harness read-only, plus one per-run output directory
     read-write.
   - It has no repository, no canonical SQLite, no labels, no Docker socket and no credentials.
   - Its network reaches the relay only.
9. **Upstream is pinned and quarantined.**
   - Hermes is pinned to `c1488ac` / 0.21.3 unless a re-probe records a new pin.
   - Untyped imports stay inside `runtime/hermes.py`.
   - Memory, session recall, skill mutation, delegation, shell, browser, generic file access and
     unrelated plugins are disabled.
   - The effective tool list is verified against an allowlist.
10. **A fake is never live evidence.** `FakeRuntime` output carries fixture provenance. G3
    requires at least one real-provider run.
11. **Every boundary is observable (A11, A14).** These are emitted as OpenTelemetry spans,
    using the mapping table in global article 27:
    - `tool.call`, with tool, args hash, result hash, bytes, `error_code` and `duration_ms`;
    - `model.call`, with `request_index`, `attempt`, `served_by`, prompt/completion tokens or
      `null`, HTTP status and `duration_ms`;
    - `stage.transition`;
    - `repair.attempt`.

    Prompt, completion and tool content goes **only** to the local Phoenix exporter (global
    article 29). The JSONL fallback gets hashes and sizes. Secrets never appear anywhere.
12. **Frozen during the run (A12/A13).**
    - Hermes' own learning features are **off**:
      - `memory.memory_enabled: false` and `memory.user_profile_enabled: false`;
      - `auxiliary.background_review.enabled: false`;
      - `curator.enabled: false`;
      - no Skills Hub installs;
      - `skills.write_approval: true`, as defence in depth;
      - `skills`, `memory`, `session_search`, terminal, file, browser, delegation and cron
        toolsets are absent from the allowlist.
    - `HERMES_HOME` is a fresh per-run tmpfs, discarded afterwards.
    - Promoted skills (M8) are mounted **read-only**. The skill-set hash is part of the
      harness hash.
    - The only learning act during a run is `propose_skill`, which produces data for the
      offline loop (global constitution, section VIII).
13. **The relay forwards an allowlist of body fields (A12).**
    - Allowed: `model`, `messages`, `tools`, `tool_choice`, `max_tokens`, `temperature`,
      `top_p`, `seed`, and `reasoning` only if M0-T04 verified it.
    - Everything else is rejected, including:
      - `plugins` (for example OpenRouter's `web` plugin);
      - `models` (fallback list);
      - a `provider` override (the relay sets its own);
      - `route` and `transforms`;
      - any `:`-suffixed model variant (for example `:online`);
      - any tool named `openrouter:*` or `web_search`.
    - These turn the relay into an internet channel, so they are refused, not stripped
      silently, and the attempt is logged.
    - Upstream concurrency is 1.
14. **Worker output is hostile input (A12).** The host reads `out/<run_id>`:
    - as regular files only (`lstat`, `O_NOFOLLOW`, never follow a symlink);
    - with size caps;
    - with strict schema validation;
    - never taking a filesystem path from file content.
