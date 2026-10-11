# M5 constitution: browser workbench and Obsidian

Inherits [../CONSTITUTION.md](../CONSTITUTION.md). The articles below add to it and never relax it.

1. **The UI is a viewer and a submitter, nothing more.**
   - Streamlit calls application services. It never contains research prompts, SQL, temporal
     policy or validation logic.
   - The 300 s research loop never runs on the render path.
2. **Reruns are free.**
   - A page rerun, tab change or browser refresh never admits a second job and never spends
     model requests.
   - Job state comes from persistence.
3. **Limitations are visible, not buried.** These are shown without opening logs:
   - unsupported or unreviewed status;
   - abstention;
   - partial or failed state;
   - unknown usage or cost;
   - the retrospective notice;
   - the fixture or live label;
   - unadjusted-price labels.
4. **Render source text safely.** Evidence text is untrusted. It is rendered as text, never as
   HTML or Markdown that could execute or inject (acceptance row A08).
5. **Scope is bounded to the selected run.**
   - Every displayed node and edge belongs to the selected snapshot or run.
   - The graph is capped at 50 nodes.
   - The relation table works even when graph layout fails.
6. **Exporters are never canonical.**
   - Obsidian output is derived and one-way, written to `generated/<run_id>/`.
   - User-owned `annotations/` are never touched.
   - Edited notes are never imported back.
   - A conflicting overwrite gives a conflict or a new destination, never a silent overwrite.
7. **Filenames come from stable IDs only.** Titles and model text never become paths. Path
   traversal is impossible by construction.
8. **Byte-stable export.** Exporting the same run unchanged produces identical bytes.
9. **Localhost only.** Streamlit is reachable from the host's loopback only in v0.1 (A15: inside the compose namespace it listens on all interfaces; the published port is `127.0.0.1` only).
10. **UI actions are observable (A11, A14).** These emit spans. Evidence text never reaches
    `spans.jsonl`:
    - job submit (`ui.submit`), through the same admission service;
    - cancel (`ui.cancel`);
    - export (`export.obsidian`), with `run_id`, file count, manifest hash and conflict
      count.

    All are OpenTelemetry spans (global article 27).
