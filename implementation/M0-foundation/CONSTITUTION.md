# M0 constitution: foundation and integration feasibility

Inherits [../CONSTITUTION.md](../CONSTITUTION.md). The articles below add to it and never relax it.

1. **Observed, not assumed.**
   - A probe records what the endpoint actually did: status codes, fields present, behaviour.
   - An advertised capability (model card, `supported_parameters`, docs) is a hypothesis until a
     probe confirms it.
2. **Live claims need live evidence.**
   - A route is `verified` only after a real call recorded in `config/runtime.lock.json` and a
     passing `live` test.
   - A missing credential means `BLOCKED`, never "probably fine".
3. **One route, no silent substitution.**
   - Exactly one research route is active, configured in `config/*.toml`.
   - Provider fallbacks (`fallback_model`, `providers_*`, OpenRouter `allow_fallbacks`) are off,
     or are recorded as unavailable.
   - The provider that actually served each call is recorded.
4. **History is kept.** Replacing a route moves the old record into history. Earlier evidence is
   never deleted.
5. **Live calls need owner approval.** A live call sends data to an external service, so
   approval comes first. Data-policy facts that are not confirmed (for example, `:free` endpoint
   logging) are recorded as unconfirmed, with the owner's acknowledgement.
6. **The Diagnose layer stays dependency-free.** Implementation diagnostics (M0-T05) and runtime
   logging (M0-T06) use only the stdlib: no OpenTelemetry, no log shippers.
7. **Diagnostics never change the code under test.** `scripts/diagnose.py` reads and runs checks.
   It never edits source or tests and never "fixes" anything.
