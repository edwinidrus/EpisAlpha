# M7 constitution: demo acceptance, recovery and handoff

Inherits [../CONSTITUTION.md](../CONSTITUTION.md). The articles below add to it and never relax it.

1. **Fix causes, never expectations.**
   - An acceptance failure is traced to the responsible module and fixed there.
   - Frozen expectations, labels and validators are not relaxed.
2. **No mislabeled evidence.**
   - A fixture is never reported as live.
   - Offline success and live success are reported separately.
   - A live check without credentials or a runtime is `BLOCKED`, never "skipped = pass".
3. **Nothing is silently incomplete.** Every acceptance row (A01–A24) and every Definition-of-
   Done item (plan §15.1) is marked passed, failed or blocked, with evidence.
4. **Smoke never touches user state.** `demo_smoke.py` uses temporary state only, and exits
   non-zero on any failed assertion.
5. **Backups restore as a unit.** The DB, object store and run directories are restored
   together, and their hashes are verified.
6. **The handoff names the next work without starting it.** That work is forward forecast
   logging, then the optional paper/evaluation lab. It is documented, not begun.
7. **The final picture is observable (A11).**
   - The final `diagnose.py` snapshot and the full `diagnose.jsonl` trend are part of the
     handoff.
   - The walkthrough run's event trail is archived with the run IDs.
