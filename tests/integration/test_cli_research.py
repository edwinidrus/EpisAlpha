"""M4-T02 — the CLI: exact commands, honest exit codes, no leaks. Fake runtime only."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from episalpha.cli import app
from episalpha.contracts.research import SnapshotManifest
from episalpha.research import services
from episalpha.settings import load_settings
from episalpha.storage.db import open_database
from episalpha.storage.repository import Repository

REPO = Path(__file__).resolve().parents[2]
SENTINEL = "sk-sentinel-provider-key-never-printed"


@pytest.fixture
def config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("EPISALPHA_TEST_KEY", SENTINEL)
    monkeypatch.delenv("EPISALPHA_FAKE_SCENARIO", raising=False)
    path = tmp_path / "test.toml"
    path.write_text(
        f'[paths]\nproject_root = "{REPO}"\ndata_root = "{tmp_path / "data"}"\n\n'
        '[provider]\nmodel_id = "vendor/model:free"\nendpoint_url = "https://openrouter.ai/api/v1"\n'
        'api_key_env = "ENV:EPISALPHA_TEST_KEY"\n'
    )
    return path


def cli(config: Path, *arguments: str) -> Any:
    result = CliRunner().invoke(app, ["--config", str(config), *arguments])
    assert SENTINEL not in result.output
    return result


def run_id_of(output: str) -> str:
    match = re.search(r"^run_id: (run-[0-9a-f]+)$", output, re.M)
    assert match, output
    return match.group(1)


def test_seed_is_idempotent(config: Path) -> None:
    first = cli(config, "demo", "seed")
    second = cli(config, "demo", "seed")
    assert first.exit_code == second.exit_code == 0
    assert first.output.splitlines()[0] == second.output.splitlines()[0]
    assert "documents 1, spans 2" in first.output
    connection = open_database(config.parent / "data" / "app.sqlite3")
    counts = [
        connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in ("entity", "instrument", "evidence_document", "evidence_span")
    ]
    connection.close()
    assert counts == [4, 4, 1, 2]


def test_fake_case_run_is_labelled_and_complete(config: Path) -> None:
    cli(config, "demo", "seed")
    result = cli(config, "research", "run", "--case", "supported", "--runtime", "fake")
    assert result.exit_code == 0, result.output
    assert result.output.startswith("[FIXTURE] fake runtime")
    assert "state: RESEARCH_COMPLETED" in result.output
    assert "notice: Retrospective research" in result.output
    assert re.search(r"^artifacts: .*/data/runs/run-[0-9a-f]+$", result.output, re.M)
    assert re.search(r"^trace: [0-9a-f]{32}$", result.output, re.M)
    run_id = run_id_of(result.output)
    status = cli(config, "research", "status", run_id)
    assert status.exit_code == 0
    assert "state: RESEARCH_COMPLETED" in status.output


def test_resubmitting_the_same_request_returns_the_same_run(config: Path) -> None:
    cli(config, "demo", "seed")
    first = cli(config, "research", "run", "--case", "supported", "--runtime", "fake")
    again = cli(config, "research", "run", "--case", "supported", "--runtime", "fake")
    assert run_id_of(first.output) == run_id_of(again.output)


@pytest.mark.parametrize(
    "arguments",
    [
        ["--case", "supported", "--snapshot", "snapshot.x", "--question", "q"],
        ["--snapshot", "snapshot.x"],
        ["--case", "supported", "--question", "q"],
        ["--case", "nonexistent"],
        ["--case", "supported", "--runtime", "gpt"],
        [],
    ],
)
def test_invalid_usage_exits_2(config: Path, arguments: list[str]) -> None:
    cli(config, "demo", "seed")
    assert cli(config, "research", "run", *arguments).exit_code == 2


@pytest.mark.parametrize(
    ("case", "scenario", "code", "state"),
    [
        ("supported", "invalid_references", 3, "REJECTED"),
        ("supported", "provider_failure", 4, "FAILED"),
        ("supported", "timeout", 4, "TIMED_OUT"),
        ("insufficient", "", 5, "ABSTAINED"),
        ("supported", "partial", 5, "PARTIAL"),
        ("supported", "cancellation", 6, "CANCELLED"),
    ],
)
def test_exit_codes_follow_the_terminal_state(
    config: Path, monkeypatch: pytest.MonkeyPatch, case: str, scenario: str, code: int, state: str
) -> None:
    if scenario:
        monkeypatch.setenv("EPISALPHA_FAKE_SCENARIO", scenario)
    cli(config, "demo", "seed")
    result = cli(config, "research", "run", "--case", case, "--runtime", "fake")
    assert result.exit_code == code, result.output
    assert f"state: {state}" in result.output


def test_snapshot_rerun_is_a_new_run(config: Path) -> None:
    cli(config, "demo", "seed")
    first = run_id_of(cli(config, "research", "run", "--case", "supported").output)
    rerun = cli(
        config,
        "research",
        "run",
        "--snapshot",
        f"snapshot.{first}",
        "--question",
        "What changed and why might it matter?",
        "--runtime",
        "fake",
    )
    assert rerun.exit_code == 0, rerun.output
    assert run_id_of(rerun.output) != first


def test_multi_instrument_snapshot_is_rejected(config: Path) -> None:
    cli(config, "demo", "seed")
    connection = open_database(config.parent / "data" / "app.sqlite3")
    Repository(connection).save_snapshot(
        SnapshotManifest(
            snapshot_id="snapshot.multi",
            snapshot_hash="d" * 64,
            instrument_ids=("synthetic-issuer.eq", "lulu.eq"),
            research_cutoff=datetime(2026, 9, 10, tzinfo=UTC),
            source_version="test",
            ontology_version=1,
            frozen_at=datetime(2026, 10, 11, tzinfo=UTC),
        )
    )
    connection.close()
    result = cli(config, "research", "run", "--snapshot", "snapshot.multi", "--question", "q?")
    assert result.exit_code == 2
    assert "one instrument" in result.output


def test_cancel_then_execute_ends_cancelled(config: Path) -> None:
    cli(config, "demo", "seed")
    workbench = services.open_workbench(load_settings(config))
    case = services.load_cases(REPO)["supported"]
    request = services.new_request(
        workbench,
        source="test",
        instrument_id=services.SYNTHETIC_INSTRUMENT,
        question=case.question,
        research_cutoff=case.research_cutoff,
        research_mode=case.research_mode,
        runtime_mode=services.RuntimeMode.FAKE,
        now=datetime(2026, 10, 11, tzinfo=UTC),
    )
    services.submit(workbench, request, {"evidence": "synthetic", "fake_scenario": "completion"})
    workbench.close()
    cancelled = cli(config, "research", "cancel", request.run_id)
    assert cancelled.exit_code == 0
    assert "cancellation requested" in cancelled.output
    executed = cli(config, "research", "execute", request.run_id)
    assert executed.exit_code == 6, executed.output
    assert "state: CANCELLED" in executed.output


def test_execute_never_admits(config: Path) -> None:
    cli(config, "demo", "seed")
    assert cli(config, "research", "execute", "run-doesnotexist").exit_code == 2


def test_hermes_case_without_ingested_filings_abstains_without_model_calls(
    config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EPISALPHA_WORKER", "local")  # the worker is never launched here
    cli(config, "demo", "seed")
    result = cli(config, "research", "run", "--case", "conflicting", "--runtime", "hermes")
    assert result.exit_code == 5, result.output
    assert "essential evidence missing" in result.output
    assert "[FIXTURE]" not in result.output
    assert "model requests 0" in result.output


def test_replay_verifies_and_reports_tampering(config: Path) -> None:
    cli(config, "demo", "seed")
    run_id = run_id_of(cli(config, "research", "run", "--case", "supported").output)
    replayed = cli(config, "replay", run_id)
    assert replayed.exit_code == 0, replayed.output
    assert "artifacts verified, no model or network calls" in replayed.output
    assert "[FIXTURE]" in replayed.output
    assert "stance: watch" in replayed.output
    (config.parent / "data" / "runs" / run_id / "records.json").write_text("{}")
    tampered = cli(config, "replay", run_id)
    assert tampered.exit_code == 4
    assert "INTEGRITY_ERROR" in tampered.output
    assert cli(config, "replay", "run-unknown").exit_code == 2


def test_snapshot_rerun_records_its_lineage(config: Path) -> None:
    cli(config, "demo", "seed")
    first = run_id_of(cli(config, "research", "run", "--case", "supported").output)
    rerun = run_id_of(
        cli(
            config,
            "research",
            "run",
            "--snapshot",
            f"snapshot.{first}",
            "--question",
            "What changed and why might it matter?",
        ).output
    )
    replayed = cli(config, "replay", rerun)
    assert f"prior run: {first}" in replayed.output


def test_recover_refuses_finished_and_unknown_runs(config: Path) -> None:
    cli(config, "demo", "seed")
    run_id = run_id_of(cli(config, "research", "run", "--case", "supported").output)
    assert cli(config, "research", "recover", run_id).exit_code == 2
    assert cli(config, "research", "recover", "run-unknown").exit_code == 2
