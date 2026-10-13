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

import json
import os
import re
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import streamlit as st

from episalpha.contracts.errors import EpisAlphaError
from episalpha.contracts.research import TERMINAL_STATES, RunState, RuntimeMode, ThesisSection
from episalpha.evaluation import reporting
from episalpha.knowledge import query
from episalpha.knowledge.export_obsidian import export_knowledge
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


def code(text: str) -> str:
    """An inline code span. Its content renders literally, so it is never ``md``-escaped; the
    fence is longer than any backtick run inside, so the text cannot close it early."""
    fence = "`" * (max(map(len, re.findall("`+", text)), default=0) + 1)
    return f"{fence} {text} {fence}"


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
    harness_hash = view.provenance.get("harness_hash")
    lines = [
        f"run: {request.run_id} ({request.research_mode.value}, cutoff "
        f"{request.research_cutoff.isoformat()})",
        f"model: {view.provenance.get('model_identifier') or 'recorded when the run ends'}",
        "served by: "
        + (", ".join(served) if served else "none (fixture)" if view.fixture else "unknown"),
        f"harness: {request.harness_id} "
        + (
            harness_hash[:16]
            if harness_hash
            else "none (fixture)"
            if view.fixture
            else "unknown"
            if view.finished
            else "hash recorded when the run ends"
        ),
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
            f"If this run stops progressing, {code(f'uv run episalpha research recover {run_id}')} "
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


# --- evidence and knowledge (M5-T02) --------------------------------------------------------


def stamp(value: datetime | None) -> str:
    return value.isoformat() if value is not None else "unknown"


def selected_knowledge(settings: Settings) -> query.RunKnowledge | None:
    """The run picked on the Research tab, read from its verified artifacts."""
    run_id = st.session_state.get("run_picker")
    if not run_id:
        st.info("No run selected. Pick one on the Research tab.")
        return None
    with opened(settings) as workbench:
        try:
            knowledge = query.load_run(workbench.repo, workbench.runs_dir, run_id)
        except EpisAlphaError as error:
            st.error(str(error))
            return None
    if knowledge is None:
        st.info(
            f"Run {run_id} has nothing to inspect yet: it is still running or froze no snapshot."
        )
        return None
    st.caption(f"run {md(run_id)} · snapshot {md(knowledge.manifest.snapshot_id)}")
    if knowledge.runtime is RuntimeMode.FAKE:
        st.warning(FIXTURE_LABEL)
    if not knowledge.persisted:
        st.warning("Validation rejected these records: saved for inspection, never persisted.")
    return knowledge


def claim_trace(trace: query.ClaimTrace) -> None:
    claim = trace.claim
    review = trace.review_status
    origin = "created by this run" if trace.in_run else "snapshot claim"
    st.markdown(
        f"**{md(claim.claim_id)}** :blue-badge[{md(claim.epistemic_status.value)}] "
        f":{REVIEW_COLORS.get(review, 'gray')}-badge[{md(review)}] · {md(origin)}"
    )
    st.text(claim.statement)
    lines = [f"attribution: {claim.attribution}", f"claim created: {stamp(claim.created_at)}"]
    if (fact := claim.numeric_fact) is not None:
        lines.append(
            f"value: {fact.metric} = {fact.value} {fact.unit} "
            f"(period {fact.period_start.date()}..{fact.period_end.date()}, "
            f"{fact.accounting_basis})"
        )
    if trace.contradicts:
        lines.append(f"contradicts: {', '.join(trace.contradicts)}")
    if trace.contradicted_by:
        lines.append(f"contradicted by: {', '.join(trace.contradicted_by)}")
    st.text("\n".join(lines))
    if (chain := trace.chain) is not None:
        st.dataframe(
            [
                {
                    "input claim": item.claim_id,
                    "value": str(item.value) if item.value is not None else "unknown",
                    "unit": item.unit or "unknown",
                    "period": f"{item.period_start.date()}..{item.period_end.date()}"
                    if item.period_start and item.period_end
                    else "unknown",
                }
                for item in chain.inputs
            ],
            hide_index=True,
        )
        method = f"{chain.method}@{chain.method_version}"
        if chain.value is None:
            st.error(f"{method} cannot be recomputed: {chain.error}")
        else:
            st.text(f"{method} = {chain.value} {chain.unit} (claimed {chain.claimed or 'nothing'})")
            if chain.matches is False:
                st.error("The claimed value does not match the registered derivation.")
            elif chain.matches:
                st.caption("Recomputed by the registered derivation; the claimed value matches.")
    for passage in trace.passages:
        span, document = passage.span, passage.document
        lines = [
            f"span {span.span_id} [{span.start_offset}:{span.end_offset}] "
            f"{span.section_locator or ''} in {span.document_id} (cited by {passage.cited_by})"
        ]
        if document is not None:
            lines += [
                f"source: {document.source_type} {document.source_uri} · "
                f"family {document.source_family_id}",
                f"published {stamp(document.published_at)} · publicly available "
                f"{stamp(document.public_available_at)} ({document.availability_basis.value}) · "
                f"captured {stamp(document.ingested_at)}",
            ]
        st.text("\n".join(lines))
        st.code(span.exact_quote, language=None, wrap_lines=True)  # untrusted: never HTML


def evidence_tab(settings: Settings) -> None:
    knowledge = selected_knowledge(settings)
    if knowledge is None:
        return
    if knowledge.thesis is None:
        st.info("This run has no thesis to drill into; the Knowledge tab lists its records.")
        return
    assertions = {a.assertion_id: a for a in knowledge.thesis.assertions}
    assertion_id = st.selectbox(
        "Assertion",
        list(assertions),
        key=f"assertion-{knowledge.run_id}",
        format_func=lambda i: f"{assertions[i].section.value} · {assertions[i].text[:90]}",
    )
    drill = query.assertion_drilldown(knowledge, str(assertion_id))
    st.text(drill.assertion.text)
    st.text(
        f"research cutoff: {stamp(drill.research_cutoff)} · "
        f"run executed: {stamp(drill.executed_at)}"
    )
    for missing in drill.missing:
        st.error(f"{missing} is not in this run's records.")
    for family, documents in drill.shared_lineage:
        st.warning(
            f"Common lineage: {md(', '.join(documents))} share source family {md(family)}. "
            "They are one source, not independent confirmations."
        )
    for trace in drill.claims:
        claim_trace(trace)
    for item in drill.hypotheses:
        hypothesis = item.hypothesis
        st.markdown(
            f"**{md(hypothesis.hypothesis_id)}** :blue-badge[hypothesized] "
            f":{REVIEW_COLORS.get(item.review_status, 'gray')}-badge[{md(item.review_status)}]"
        )
        st.text(
            "\n".join(
                [
                    f"mechanism: {hypothesis.mechanism}",
                    *(f"assumption: {a}" for a in hypothesis.assumptions),
                    f"falsified if: {hypothesis.falsification_condition}",
                    f"supporting: {', '.join(hypothesis.supporting_claim_ids) or 'none'}",
                    f"opposing: {', '.join(hypothesis.opposing_claim_ids) or 'none'}",
                    f"horizon: {hypothesis.horizon_trading_days} trading days",
                ]
            )
        )


def knowledge_tab(settings: Settings) -> None:
    knowledge = selected_knowledge(settings)
    if knowledge is None:
        return
    st.subheader("Relations")
    st.caption(
        "UPPERCASE labels are relation predicates. Origin 'recorded' is a stored relation; other "
        "origins name the record whose fields imply the edge. 'cites' and 'derivation input' are "
        "references, not relations."
    )
    st.dataframe([asdict(row) for row in query.relation_table(knowledge)], hide_index=True)
    st.subheader("Graph")
    limit = settings.limits.max_graph_nodes
    graph = query.local_graph(knowledge, limit=limit)
    if graph.truncated:
        st.warning(f"Graph cut at {limit} nodes around the thesis; the relation table is complete.")
    try:
        st.graphviz_chart(query.to_dot(graph))
    except Exception as error:  # noqa: BLE001 - the table above must survive any layout failure
        st.warning(f"Graph layout failed ({type(error).__name__}); the relation table is complete.")
    export_section(settings, knowledge)


def export_section(settings: Settings, knowledge: query.RunKnowledge) -> None:
    st.subheader("Obsidian")
    vault = settings.paths.data_root / "exports" / "vault"
    st.caption(
        f"One-way export to {code(str(vault))}: notes are rewritten byte-identically, "
        "`annotations/` is never touched, and an edited note moves the export to a new folder."
    )
    if st.button("Export to Obsidian vault", key=f"export-{knowledge.run_id}"):
        try:
            result = export_knowledge(knowledge, vault)
        except EpisAlphaError as error:
            st.error(str(error))
            return
        st.success(
            f"Exported {result.files} files to "
            f"{code(result.destination.relative_to(vault.resolve()).as_posix())}."
        )
        for name in result.conflicts:
            st.warning(f"Edited note left untouched: generated/{md(name)}")


# --- experiments (M6-T04) ------------------------------------------------------------------


def experiments_tab(settings: Settings) -> None:
    found = {p.name: p for p in reporting.list_campaigns(settings.paths.data_root / "campaigns")}
    if not found:
        st.info(
            "No campaign yet. Run "
            + code("uv run episalpha experiment compare --campaign demo-v1 --runtime fake")
            + "."
        )
        return
    chosen = st.selectbox("Campaign", list(found), key="campaign_picker")
    report = reporting.build_report(found[str(chosen)])
    st.warning(reporting.DISCLAIMER)
    if report.runtime == "fake":
        st.warning(FIXTURE_LABEL)
    st.text(
        f"{report.name} · campaign {report.campaign_id} · runtime {report.runtime} · "
        f"model {report.model} · status {report.status}"
    )
    if report.decision == "baseline_retained":
        st.badge("Challenger rejected · baseline retained", color="gray")
        st.caption("A rejected challenger is a complete, valid result.")
    elif report.decision == "challenger_passed":
        st.badge("Challenger cleared every gate · baseline still active", color="blue")
        st.caption("Promotion is an explicit owner action, versioned and linked to this report.")
    st.subheader("Gates")
    columns = st.columns(max(1, min(3, len(report.gates))))
    for index, gate in enumerate(report.gates):
        with columns[index % len(columns)].container(border=True):
            st.badge(
                "PASS" if gate["passed"] else "FAIL", color="green" if gate["passed"] else "red"
            )
            st.text(f"{gate['gate']}\n{gate['detail']}")
    st.subheader("Every trial")
    st.dataframe(
        [
            {
                "phase": t.phase,
                "variant": t.variant,
                "case": t.case_id,
                "attempt": t.attempt,
                "status": t.status,
                "state": t.state,
                "error": t.error,
                "requests": t.model_requests,
                "latency s": t.latency_seconds,
                **{k: f"{n}/{d}" if d else "N/A" for k, (n, d) in t.metrics.items()},
                "run": t.run_id,
            }
            for t in report.trials
        ],
        hide_index=True,
    )
    st.subheader("Aggregates (numerator/denominator)")
    st.dataframe(
        [
            {
                "phase": a.phase,
                "variant": a.variant,
                "trials": a.trials,
                "interrupted": a.interrupted,
                **{k: f"{n}/{d}" if d else "N/A" for k, (n, d) in a.metrics.items()},
                "requests": a.model_requests,
                "tokens": a.tokens,
                "cost": a.cost,
            }
            for a in report.aggregates
        ],
        hide_index=True,
    )
    if report.candidate_diff is not None:
        st.subheader("Candidate")
        st.code(json.dumps(report.candidate_diff, indent=2, sort_keys=True), language="json")
    for warning in report.reuse_warnings:
        st.error(warning)
    if report.exposed_final_cases:
        st.text("final-check cases exposed: " + ", ".join(report.exposed_final_cases))
    st.download_button(
        "Download report (Markdown)",
        reporting.render_markdown(report),
        file_name=f"{report.campaign_id}.md",
        key="report_download",
    )


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
        evidence_tab(settings)
    with knowledge:
        knowledge_tab(settings)
    with experiments:
        experiments_tab(settings)


main()
