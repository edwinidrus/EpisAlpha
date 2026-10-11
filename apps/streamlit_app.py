"""EpisAlpha browser workbench (plan M5-T01): a viewer and a submitter, nothing more.

    uv run streamlit run apps/streamlit_app.py      # binds 127.0.0.1 (.streamlit/config.toml)

- Job state always comes from persistence (SQLite and the run's artifacts), never from the
  browser session. Only the form's submit button admits a job, and ``services.launch`` starts its
  worker at most once, so reruns, tab changes and page refreshes never start a second job or
  spend a model request. The research loop never runs on the render path.
- Model and evidence text is untrusted: it is rendered with ``st.text`` (no Markdown, no HTML).
  Markdown widgets only ever show app-generated labels, escaped.
- No SQL, prompts, temporal policy or validation here: everything goes through
  :mod:`episalpha.research.services`.
"""

from __future__ import annotations

import os
import re
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import streamlit as st

from episalpha.contracts.errors import EpisAlphaError
from episalpha.contracts.research import TERMINAL_STATES, RunState, RuntimeMode, ThesisSection
from episalpha.observability import SpanKind, annotate, configure_tracing, span
from episalpha.research import services
from episalpha.settings import Settings, load_settings

CONFIG = Path(os.environ.get("EPISALPHA_CONFIG") or "config/demo.toml")
REFRESH_SECONDS = 2  # status polling while a run is active; reads only
FIXTURE_LABEL = "[FIXTURE] fake runtime: scripted fixture output, not research"
LIVE_LABEL = "LIVE: Hermes worker through the model relay; each stage spends model requests"

Color = Literal["red", "orange", "blue", "green", "gray"]
BADGES: dict[RunState, tuple[str, Color]] = {
    RunState.QUEUED: ("Queued", "gray"),
    RunState.SNAPSHOT_FROZEN: ("Running · snapshot frozen", "blue"),
    RunState.RESEARCHING: ("Running · researching", "blue"),
    RunState.CRITIQUING: ("Running · critiquing", "blue"),
    RunState.SYNTHESIZING: ("Running · synthesizing", "blue"),
    RunState.VALIDATING: ("Running · validating", "blue"),
    RunState.RESEARCH_COMPLETED: ("Completed", "green"),
    RunState.ABSTAINED: ("Abstained", "orange"),
    RunState.PARTIAL: ("Partial", "orange"),
    RunState.REJECTED: ("Rejected", "red"),
    RunState.FAILED: ("Failed", "red"),
    RunState.TIMED_OUT: ("Timed out", "red"),
    RunState.CANCELLED: ("Cancelled", "gray"),
}
REVIEW_COLORS: dict[str, Color] = {
    "supported": "green",
    "partially_supported": "orange",
    "unsupported": "red",
    "unreviewed": "gray",
}
STANCE_COLORS: dict[str, Color] = {"investigate": "blue", "watch": "orange", "abstain": "gray"}
_MARKDOWN_SPECIAL = re.compile(r"([\\`*_{}\[\]()#+\-.!|<>~$:])")


def md(label: str) -> str:
    """Escape an app-generated label (an ID, a vocabulary term) for a Markdown widget."""
    return _MARKDOWN_SPECIAL.sub(r"\\\1", label)


def now() -> datetime:
    return datetime.now(UTC)


@contextmanager
def opened(settings: Settings) -> Iterator[services.Workbench]:
    # One short-lived connection per render: Streamlit reruns on other threads.
    workbench = services.open_workbench(settings)
    try:
        yield workbench
    finally:
        workbench.close()


# --- submission ----------------------------------------------------------------------------


def submit_form(settings: Settings) -> None:
    st.subheader("New research job")
    nonce = st.session_state.setdefault("form_nonce", secrets.token_hex(8))
    with opened(settings) as workbench:
        cases = services.load_cases(workbench.project_root)
    with st.form("research_form"):
        source = st.radio(
            "Evidence", ["Demo case", "Existing snapshot"], key="source", horizontal=True
        )
        case = st.selectbox("Demo case", sorted(cases), key="case")
        st.caption("Fake runs read the synthetic corpus, never the case's real filings.")
        snapshot = st.text_input("Snapshot ID (rerun only)", key="snapshot")
        question = st.text_area("Question (rerun only; a case carries its own)", key="question")
        runtime = st.radio(
            "Runtime",
            [mode.value for mode in RuntimeMode],
            key="runtime",
            horizontal=True,
            captions=["scripted fixture, no model", "live model requests"],
        )
        submitted = st.form_submit_button("Submit research job", key="submit", type="primary")
    if not submitted:
        return
    mode = RuntimeMode(runtime)
    with span("ui.submit", SpanKind.CHAIN, **{"episalpha.runtime_mode": mode.value}) as current:
        with opened(settings) as workbench:
            try:
                if source == "Existing snapshot":
                    request, plan = services.plan_snapshot(
                        workbench, snapshot.strip(), question, mode, now=now(), nonce=nonce
                    )
                else:
                    request, plan = services.plan_case(
                        workbench, str(case), mode, now=now(), nonce=nonce
                    )
                record = services.submit(workbench, request, plan)
                run_id = record.request.run_id
                launched = services.launch(workbench, run_id, CONFIG, now=now())
            except EpisAlphaError as error:
                annotate(current, **{"episalpha.refused": error.code.value})
                st.error(str(error))
                return
        annotate(
            current,
            **{"session.id": run_id, "episalpha.run_id": run_id, "episalpha.launched": launched},
        )
    st.session_state["run_picker"] = run_id
    if launched:
        st.success(f"Submitted {run_id}; a worker is executing it.")
    else:
        st.info(f"This form already submitted {run_id}. Reload the page to start a new job.")


# --- status --------------------------------------------------------------------------------


def status_panel(settings: Settings, run_id: str, was_active: bool) -> None:
    with opened(settings) as workbench:
        view = services.run_view(workbench, run_id, now=now())
    if was_active and view.finished:
        st.rerun()  # stop polling and refresh the run list
    record = view.record
    request = record.request
    label, color = BADGES[record.state]
    st.badge(label, color=color)
    if view.fixture:
        st.warning(FIXTURE_LABEL)
    else:
        st.info(LIVE_LABEL)
    if view.notice:
        st.warning(view.notice)
    if record.reason:
        st.text(f"reason: {record.reason}")
    if record.error_code is not None:
        st.text(f"error_code: {record.error_code.value}")
    for warning in record.warnings:
        st.text(f"warning: {warning}")
    served = view.provenance.get("served_by") or []
    lines = [
        f"run: {request.run_id} ({request.research_mode.value}, cutoff "
        f"{request.research_cutoff.isoformat()})",
        f"model: {view.provenance.get('model_identifier') or 'recorded when the run ends'}",
        "served by: "
        + (", ".join(served) if served else "none (fixture)" if view.fixture else "unknown"),
        f"harness: {request.harness_id} "
        f"{(view.provenance.get('harness_hash') or 'hash recorded when the run ends')[:16]}",
        f"elapsed: {view.elapsed_seconds} s",
        "usage: "
        + (services.usage_line(record.usage) if view.finished else "recorded when the run ends"),
    ]
    if record.snapshot_id:
        lines.append(f"snapshot: {record.snapshot_id}")
    if view.provenance.get("prior_run_id"):
        lines.append(f"prior run: {view.provenance['prior_run_id']}")
    st.text("\n".join(lines))
    if view.trace_link:
        st.link_button("Open trace in Phoenix", view.trace_link)
    if not view.finished:
        if st.button("Cancel run", key="cancel"):
            with span("ui.cancel", SpanKind.CHAIN, **{"episalpha.run_id": run_id}):
                with opened(settings) as workbench:
                    services.cancel(workbench, run_id, now=now())
            st.success("Cancellation requested; the runner stops before its next stage.")
        st.caption(
            f"If this run stops progressing, `uv run episalpha research recover {md(run_id)}` "
            "resumes it as a new attempt."
        )
    if view.integrity_error:
        st.error(view.integrity_error)
    elif view.verified_artifacts:
        st.caption(
            f"Saved replay: {view.verified_artifacts} artifacts verified, "
            "no model or network calls."
        )
    if view.stages:
        st.dataframe(
            [
                {
                    "stage": stage.stage.value,
                    "completed": stage.completed,
                    "exit": stage.exit_reason,
                    "model requests": stage.usage.model_requests,
                    "tool calls": stage.usage.tool_calls,
                    "started": stage.started_at.isoformat(),
                }
                for stage in view.stages
            ],
            hide_index=True,
        )
    thesis_section(view)


def thesis_section(view: services.RunView) -> None:
    thesis = view.thesis
    if thesis is None:
        return
    st.subheader("Thesis")
    st.badge(f"stance: {thesis.stance.value}", color=STANCE_COLORS[thesis.stance.value])
    for section in ThesisSection:
        assertions = [item for item in view.assertions if item.section is section]
        if not assertions:
            continue
        st.markdown(f"**{md(section.value.replace('_', ' ').capitalize())}**")
        for assertion in assertions:
            st.text(assertion.text)
            st.markdown(
                " ".join(
                    f":{REVIEW_COLORS.get(ref.review_status, 'gray')}-badge["
                    f"{md(ref.record_id)} · {md(ref.epistemic_status)} · "
                    f"{md(ref.review_status)}]"
                    for ref in assertion.references
                )
            )
    for item in thesis.missing_information:
        st.text(f"missing: {item}")
    st.text(f"next inquiry: {thesis.next_inquiry}")


# --- page ----------------------------------------------------------------------------------


def research_tab(settings: Settings) -> None:
    form_column, status_column = st.columns([1, 2], gap="large")
    with form_column:
        submit_form(settings)
    with status_column:
        with opened(settings) as workbench:
            runs = services.recent_runs(workbench)
        if not runs:
            st.info("No runs yet. Submit one with the form.")
            return
        states = {run.request.run_id: run.state for run in runs}
        if st.session_state.get("run_picker") not in states:
            st.session_state["run_picker"] = runs[0].request.run_id
        run_id = st.selectbox(
            "Run", list(states), key="run_picker", format_func=lambda i: f"{i} · {states[i].value}"
        )
        active = states[run_id] not in TERMINAL_STATES
        st.fragment(run_every=REFRESH_SECONDS if active else None)(status_panel)(
            settings, run_id, active
        )


def main() -> None:
    st.set_page_config(page_title="EpisAlpha", layout="wide")
    st.title("EpisAlpha")
    if not CONFIG.is_file():
        st.error(f"settings file {CONFIG} not found; set EPISALPHA_CONFIG")
        return
    settings = load_settings(CONFIG)
    configure_tracing(settings)
    research, evidence, knowledge, experiments = st.tabs(
        ["Research", "Evidence", "Knowledge", "Experiments"]
    )
    with research:
        research_tab(settings)
    with evidence:
        st.info("Not built yet: evidence inspection and the local graph arrive in M5-T02.")
    with knowledge:
        st.info("Not built yet: knowledge views and the Obsidian export arrive in M5-T02/T03.")
    with experiments:
        st.info("Not built yet: baseline-versus-challenger reports arrive in M6-T04.")


main()
