"""M5-T04 — the six-minute walkthrough, core navigation (plan section 11, M5-T04).

Each test is one walkthrough step that the owner performs in the browser, replayed under
``AppTest``. Runs come from the fake runtime: labelled fixtures, never evidence of live research.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from episalpha.contracts.research import RuntimeMode
from episalpha.observability import shutdown_tracing
from episalpha.research import services
from episalpha.settings import load_settings

REPO = Path(__file__).resolve().parents[2]
APP = REPO / "apps" / "streamlit_app.py"
NOW = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)
DEMAND = "Management expects demand to soften during the first half."


@pytest.fixture
def config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    path = tmp_path / "test.toml"
    path.write_text(f'[paths]\nproject_root = "{REPO}"\ndata_root = "{tmp_path / "data"}"\n')
    monkeypatch.setenv("EPISALPHA_CONFIG", str(path))
    workbench = services.open_workbench(load_settings(path))
    services.seed_demo(workbench)
    workbench.close()
    yield path
    shutdown_tracing()


def fake_run(config: Path, monkeypatch: pytest.MonkeyPatch, scenario: str) -> str:
    monkeypatch.setenv("EPISALPHA_FAKE_SCENARIO", scenario)
    workbench = services.open_workbench(load_settings(config))
    try:
        request, plan = services.plan_case(
            workbench, "supported", RuntimeMode.FAKE, now=NOW, nonce=f"walk-{scenario}"
        )
        services.submit(workbench, request, plan)
        services.execute(workbench, request.run_id, worker_id="test", now=lambda: NOW)
        return request.run_id
    finally:
        workbench.close()


def texts(at: AppTest) -> str:
    return "\n".join(str(item.value) for item in at.text)


def test_assertion_to_original_passage_takes_at_most_three_interactions(
    config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_id = fake_run(config, monkeypatch, "completion")
    at = AppTest.from_file(str(APP), default_timeout=30).run()
    assert at.selectbox(key="run_picker").value == run_id  # the newest run is preselected
    interactions = 0
    # 1. Open the Evidence tab. AppTest renders every tab, so this click has no call to make.
    interactions += 1
    # 2 and 3. Open the assertion picker and choose the interpretation.
    picker = at.selectbox(key=f"assertion-{run_id}")
    target = next(option for option in picker.options if option.startswith("interpretation"))
    picker.select(target)
    at.run()
    interactions += 2
    assert not at.exception, at.exception
    assert interactions <= 3
    passages = [str(item.value) for item in at.code]
    assert DEMAND in passages  # the original passage, as quoted in the source


def test_missing_information_is_visible_on_the_research_tab(
    config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_run(config, monkeypatch, "completion")
    at = AppTest.from_file(str(APP), default_timeout=30).run()
    shown = texts(at)
    assert "missing: Order-book size for the first half is not disclosed in the snapshot." in shown
    assert "next inquiry:" in shown


def test_status_lines_are_never_cut_mid_word(config: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_run(config, monkeypatch, "completion")
    at = AppTest.from_file(str(APP), default_timeout=30).run()
    harness = next(line for line in texts(at).splitlines() if line.startswith("harness:"))
    # A fixture run never gets a harness hash; the line says so instead of a sliced sentence.
    assert harness == "harness: harness.baseline none (fixture)"


def test_demo_corpus_quotes_are_whole_sentences() -> None:
    # Walkthrough step "inspect a quote": a passage cut mid-word ("...million. Ma",
    # "agement expects...") reads as a broken citation, even with consistent offsets.
    corpus = json.loads((REPO / services.SYNTHETIC_CORPUS).read_text())
    for span in corpus["spans"]:
        text = corpus["document_texts"][span["document_id"]]
        quote = span["exact_quote"]
        assert text[span["start_offset"] : span["end_offset"]] == quote
        assert quote == quote.strip() and re.match(r"[A-Z0-9]", quote), span["span_id"]
        assert quote.endswith((".", "!", "?")), span["span_id"]


def test_paths_in_code_spans_render_verbatim(config: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Markdown escapes are not processed inside a code span: an escaped path shows its
    # backslashes ("pytest\-of\-...") and copies as a path that does not exist.
    run_id = fake_run(config, monkeypatch, "completion")
    at = AppTest.from_file(str(APP), default_timeout=30).run()
    vault = load_settings(config).paths.data_root / "exports" / "vault"
    caption = next(str(c.value) for c in at.caption if "One-way export" in str(c.value))
    assert f"` {vault} `" in caption
    at.button(key=f"export-{run_id}").click().run()
    success = next(str(s.value) for s in at.success if "Exported" in str(s.value))
    assert f"` generated/{run_id} `" in success


def test_the_experiments_tab_shows_disclaimer_gates_and_every_trial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Walkthrough step 7 (M6-T04): a fake campaign, read back from its ledger.
    from episalpha.evaluation.reporting import DISCLAIMER
    from episalpha.evolution.campaign import compare

    sealed = tmp_path / "sealed"
    sealed.mkdir()
    for draft in (REPO / "docs/implementation/m6-label-drafts/development").glob("*.json"):
        (sealed / draft.name).write_bytes(draft.read_bytes())
    path = tmp_path / "test.toml"
    path.write_text(
        f'[paths]\nproject_root = "{REPO}"\ndata_root = "{tmp_path / "data"}"\n\n'
        f'[evaluation]\nlabels_dir = "{sealed}"\n'
    )
    monkeypatch.setenv("EPISALPHA_CONFIG", str(path))
    monkeypatch.setenv("EPISALPHA_FAKE_SCENARIO", "completion")
    workbench = services.open_workbench(load_settings(path))
    try:
        services.seed_demo(workbench)
        result = compare(workbench, "demo-v1", RuntimeMode.FAKE, now=lambda: NOW)
    finally:
        workbench.close()
    at = AppTest.from_file(str(APP), default_timeout=30).run()
    assert not at.exception, at.exception
    assert at.selectbox(key="campaign_picker").value == result.campaign_id
    assert DISCLAIMER in [str(w.value) for w in at.warning]
    shown = texts(at)
    assert "0 validation cases exist" in shown and "3 contradiction gain" in shown
    assert ":gray-badge[Challenger rejected · baseline retained]" in "\n".join(
        str(m.value) for m in at.markdown
    )
    trials = at.dataframe[-2].value  # every trial, then aggregates
    assert len(trials) == 4 and set(trials["status"]) == {"scored"}
