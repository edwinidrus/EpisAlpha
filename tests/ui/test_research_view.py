"""M5-T01 — the browser research view: reruns are free, state comes from persistence.

The Streamlit script runs under ``AppTest`` against a real workbench in ``tmp_path``. Only the
detached worker launch is replaced (``services._spawn``), so admission, idempotency and the
launch-once marker are the real ones. Runs in each state are produced in-process with the fake
runtime: every one of them is a labelled fixture, never evidence of a live integration.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from streamlit.testing.v1 import AppTest

from episalpha.contracts.research import RETROSPECTIVE_NOTICE, RunState, RuntimeMode
from episalpha.observability import shutdown_tracing
from episalpha.research import services
from episalpha.research.runner import cancel_requested, claim
from episalpha.settings import load_settings
from episalpha.storage.db import transaction

REPO = Path(__file__).resolve().parents[2]
APP = REPO / "apps" / "streamlit_app.py"
NOW = datetime(2026, 10, 11, 9, 0, tzinfo=UTC)


@pytest.fixture
def config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setenv("EPISALPHA_TEST_KEY", "sk-sentinel-provider-key-never-printed")
    monkeypatch.delenv("EPISALPHA_FAKE_SCENARIO", raising=False)
    path = tmp_path / "test.toml"
    path.write_text(
        f'[paths]\nproject_root = "{REPO}"\ndata_root = "{tmp_path / "data"}"\n\n'
        '[provider]\nmodel_id = "vendor/model:free"\nendpoint_url = "https://openrouter.ai/api/v1"\n'
        'api_key_env = "ENV:EPISALPHA_TEST_KEY"\n'
    )
    monkeypatch.setenv("EPISALPHA_CONFIG", str(path))
    workbench = services.open_workbench(load_settings(path))
    services.seed_demo(workbench)
    workbench.close()
    yield path
    shutdown_tracing()


@pytest.fixture
def launches(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    calls: list[list[str]] = []
    monkeypatch.setattr(services, "_spawn", lambda command, cwd, log: calls.append(command))
    return calls


def workbench_for(config: Path) -> services.Workbench:
    return services.open_workbench(load_settings(config))


def app() -> AppTest:
    return AppTest.from_file(str(APP), default_timeout=30).run()


def submit(at: AppTest, case: str = "supported", runtime: str = "fake") -> AppTest:
    at.selectbox(key="case").set_value(case)
    at.radio(key="runtime").set_value(runtime)
    at.button(key="submit").click()
    return at.run()


def markdown(at: AppTest) -> str:
    return "\n".join(str(item.value) for item in at.markdown)


def texts(at: AppTest) -> str:
    return "\n".join(str(item.value) for item in at.text)


def everything(at: AppTest) -> str:
    parts = [markdown(at), texts(at)]
    for kind in ("caption", "info", "warning", "error", "success"):
        parts.extend(str(item.value) for item in getattr(at, kind))
    return "\n".join(parts)


def run_count(config: Path) -> int:
    workbench = workbench_for(config)
    try:
        return len(services.recent_runs(workbench, limit=100))
    finally:
        workbench.close()


# --- reruns are free ---------------------------------------------------------------------------


def test_submit_then_reruns_and_refresh_admit_and_launch_exactly_once(
    config: Path, launches: list[list[str]]
) -> None:
    at = submit(app())
    assert not at.exception, at.exception
    for _ in range(3):
        at.run()
    at.button(key="submit").click().run()  # the same form again: the same run, no second launch
    refreshed = app()  # a browser refresh is a fresh session reading persistence
    assert run_count(config) == 1
    assert len(launches) == 1
    command = launches[0]
    assert command[-3:-1] == ["research", "execute"]
    assert "--config" in command
    run_id = command[-1]
    assert refreshed.selectbox(key="run_picker").value == run_id
    assert "Queued" in markdown(refreshed)


def test_a_second_job_while_one_is_active_is_refused_visibly(
    config: Path, launches: list[list[str]]
) -> None:
    submit(app())
    other = submit(app(), case="insufficient")  # a new session: a new form nonce
    assert any("already active" in str(item.value) for item in other.error)
    assert run_count(config) == 1
    assert len(launches) == 1


# --- every state is visible --------------------------------------------------------------------


def finished_run(config: Path, monkeypatch: pytest.MonkeyPatch, scenario: str, case: str) -> str:
    monkeypatch.setenv("EPISALPHA_FAKE_SCENARIO", scenario)
    workbench = workbench_for(config)
    try:
        request, plan = services.plan_case(
            workbench, case, RuntimeMode.FAKE, now=NOW, nonce=f"test-{scenario}-{case}"
        )
        services.submit(workbench, request, plan)
        record = services.execute(workbench, request.run_id, worker_id="test", now=lambda: NOW)
        return record.request.run_id
    finally:
        workbench.close()
        monkeypatch.delenv("EPISALPHA_FAKE_SCENARIO")


def running_run(config: Path, runtime: RuntimeMode = RuntimeMode.FAKE) -> str:
    workbench = workbench_for(config)
    try:
        request, plan = services.plan_case(
            workbench, "supported", runtime, now=NOW, nonce="test-running"
        )
        record = services.submit(workbench, request, plan)
        claim(workbench.repo, request.run_id, "test", now=NOW)
        for state in (RunState.SNAPSHOT_FROZEN, RunState.RESEARCHING):
            record = record.model_copy(update={"state": record.transition(state)})
            with transaction(workbench.repo.connection):
                workbench.repo.update_run(record)
        return request.run_id
    finally:
        workbench.close()


def select(at: AppTest, run_id: str) -> AppTest:
    at.selectbox(key="run_picker").set_value(run_id)
    return at.run()


@pytest.mark.parametrize(
    ("scenario", "case", "badge"),
    [
        ("completion", "supported", ":green-badge[Completed]"),
        ("abstention", "insufficient", ":orange-badge[Abstained]"),
        ("partial", "supported", ":orange-badge[Partial]"),
        ("invalid_references", "supported", ":red-badge[Rejected]"),
        ("provider_failure", "supported", ":red-badge[Failed]"),
        ("timeout", "supported", ":red-badge[Timed out]"),
        ("cancellation", "supported", ":gray-badge[Cancelled]"),
    ],
)
def test_each_terminal_state_renders_its_badge_and_reason(
    config: Path, monkeypatch: pytest.MonkeyPatch, scenario: str, case: str, badge: str
) -> None:
    run_id = finished_run(config, monkeypatch, scenario, case)
    at = select(app(), run_id)
    assert not at.exception, at.exception
    assert badge in markdown(at)
    workbench = workbench_for(config)
    record = workbench.repo.get_run(run_id)
    workbench.close()
    assert record is not None and record.reason[:40] in everything(at)
    assert at.get("button") == [] or all(b.key != "cancel" for b in at.button)


def test_a_running_run_shows_its_badge_stage_and_cancel(config: Path) -> None:
    run_id = running_run(config)
    at = select(app(), run_id)
    assert ":blue-badge[Running · researching]" in markdown(at)
    assert "usage: recorded when the run ends" in everything(at)
    at.button(key="cancel").click().run()
    assert any("Cancellation requested" in str(item.value) for item in at.success)
    workbench = workbench_for(config)
    try:
        assert cancel_requested(workbench.repo, run_id)
    finally:
        workbench.close()


# --- limitations are visible -------------------------------------------------------------------


def test_fixture_label_unknown_usage_notice_and_thesis_from_assertions(
    config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_id = finished_run(config, monkeypatch, "completion", "supported")
    at = select(app(), run_id)
    shown = everything(at)
    assert "[FIXTURE] fake runtime" in shown
    assert "LIVE" not in shown
    assert "tokens (prompt/completion) unknown, cost unknown" in shown
    assert "(prompt/completion) 0" not in shown and "cost 0" not in shown
    assert RETROSPECTIVE_NOTICE in shown
    assert "Saved replay" in shown and "artifacts verified" in shown
    assert "model: fixture" in shown
    assert "harness: harness.baseline" in shown
    assert "elapsed:" in shown
    workbench = workbench_for(config)
    view = services.replay_run(workbench, run_id)
    workbench.close()
    assert view.thesis is not None
    for assertion in view.thesis["assertions"]:
        assert assertion["text"] in texts(at)  # untrusted text goes through st.text, unparsed
        for claim_id in assertion["claim_ids"]:
            assert f"{claim_id}".replace(".", "\\.").replace("-", "\\-") in markdown(at)
    assert "unreviewed" in markdown(at)


def test_live_runs_are_labelled_live(config: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EPISALPHA_WORKER", "local")  # admission checks a worker exists; none runs
    run_id = running_run(config, RuntimeMode.HERMES)
    shown = everything(select(app(), run_id))
    assert "LIVE" in shown
    assert "[FIXTURE]" not in shown


def test_trace_link_only_when_phoenix_is_configured(
    config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_id = finished_run(config, monkeypatch, "completion", "supported")
    at = select(app(), run_id)
    assert [e for e in at.get("link_button")] == []
    monkeypatch.setattr(
        services, "trace_url", lambda trace_id: f"http://127.0.0.1:6006/redirects/traces/{trace_id}"
    )
    linked = select(app(), run_id)
    buttons = linked.get("link_button")
    assert [b.proto.label for b in buttons] == ["Open trace in Phoenix"]
    assert buttons[0].proto.url.startswith("http://127.0.0.1:6006/redirects/traces/")


def test_integrity_errors_are_shown_not_hidden(
    config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_id = finished_run(config, monkeypatch, "completion", "supported")
    (config.parent / "data" / "runs" / run_id / "records.json").write_text("{}")
    at = select(app(), run_id)
    assert any("INTEGRITY_ERROR" in str(item.value) for item in at.error)


# --- UI actions are observable ----------------------------------------------------------------


def test_submit_and_cancel_emit_ui_spans(config: Path, launches: list[list[str]]) -> None:
    at = submit(app())
    at.button(key="cancel").click().run()
    shutdown_tracing()
    lines = (config.parent / "data" / "logs" / "spans.jsonl").read_text().splitlines()
    spans = [json.loads(line) for line in lines]
    by_name: dict[str, list[dict[str, Any]]] = {}
    for item in spans:
        by_name.setdefault(item["name"], []).append(item)
    assert len(by_name["ui.submit"]) == 1 and len(by_name["ui.cancel"]) == 1
    run_id = launches[0][-1]
    assert by_name["ui.submit"][0]["attributes"]["episalpha.run_id"] == run_id
    assert by_name["ui.submit"][0]["attributes"]["episalpha.launched"] is True


# --- M5-T02: evidence drilldown and run graph ---------------------------------------------------


def test_evidence_tab_drills_from_assertion_to_passage_and_knowledge_tab_shows_relations(
    config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_id = finished_run(config, monkeypatch, "completion", "supported")
    at = select(app(), run_id)
    assert not at.exception, at.exception
    codes = [str(item.value) for item in at.code]
    assert "Fourth quarter revenue reached EUR 412.0 million. Ma" in codes  # first assertion
    assert ":gray-badge[unreviewed]" in markdown(at)
    assert "contradicted by:" in texts(at)  # A02: the critic's contradiction is visible
    table = at.dataframe[-1].value
    assert "CONTRADICTS" in set(table["label"]) and "recorded" in set(table["origin"])
    assert all(
        node.startswith(run_id) or not node.startswith("run-")
        for node in (*table["source_id"], *table["target_id"])
    )
    assert len(at.get("graphviz_chart")) == 1


def test_html_in_a_passage_is_rendered_as_inert_text(
    config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fixtures.run_knowledge as fixtures_query  # SYNTHETIC RunKnowledge, HTML in a span

    from episalpha.knowledge import query

    run_id = finished_run(config, monkeypatch, "completion", "supported")
    monkeypatch.setattr(query, "load_run", lambda *_: fixtures_query.knowledge())
    at = select(app(), run_id)
    at.selectbox(key=f"assertion-{fixtures_query.RUN}").set_value(f"{fixtures_query.RUN}.a2").run()
    assert not at.exception, at.exception
    assert fixtures_query.SCRIPT in [str(item.value) for item in at.code]
    assert "<script>" not in markdown(at)
    assert all(not getattr(item.proto, "allow_html", False) for item in at.markdown)
    assert "Common lineage" in "\n".join(str(item.value) for item in at.warning)  # A21
    assert "pct\\_change@1" not in markdown(at) and "pct_change@1 = " in texts(at)  # A8 chain


def test_relation_table_survives_a_graph_failure(
    config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from episalpha.knowledge import query

    def broken(graph: query.Graph) -> str:
        raise RuntimeError("layout")

    run_id = finished_run(config, monkeypatch, "completion", "supported")
    monkeypatch.setattr(query, "to_dot", broken)
    at = select(app(), run_id)
    assert not at.exception, at.exception
    assert "CONTRADICTS" in set(at.dataframe[-1].value["label"])
    assert any("Graph layout failed" in str(item.value) for item in at.warning)


def test_knowledge_tab_exports_the_run_to_the_vault(
    config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_id = finished_run(config, monkeypatch, "completion", "supported")
    at = select(app(), run_id)
    at.button(key=f"export-{run_id}").click().run()
    assert not at.exception, at.exception
    assert any("Exported" in str(item.value) for item in at.success)
    vault = config.parent / "data" / "exports" / "vault"
    assert (vault / "generated" / run_id / "manifest.json").is_file()
    assert (vault / "annotations").is_dir()
    before = {p: p.read_bytes() for p in (vault / "generated").rglob("*") if p.is_file()}
    at.button(key=f"export-{run_id}").click().run()  # again: byte-identical, same folder
    after = {p: p.read_bytes() for p in (vault / "generated").rglob("*") if p.is_file()}
    assert after == before
