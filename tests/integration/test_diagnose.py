"""Pure-function tests for ``scripts/diagnose.py`` (M0-T05).

The script is loaded by path because ``scripts/`` is not a package. Nothing here runs the real
checks; ``main()`` is exercised by running the script itself, as recorded in the task journal.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def diagnose() -> ModuleType:
    path = REPO_ROOT / "scripts" / "diagnose.py"
    spec = importlib.util.spec_from_file_location("diagnose", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUFF_JSON = json.dumps(
    [
        {"code": "E501", "filename": "/r/src/a.py", "message": "Line too long"},
        {"code": "E501", "filename": "/r/src/b.py", "message": "Line too long"},
        {"code": "F401", "filename": "/r/src/a.py", "message": "unused import"},
    ]
)

JUNIT = """<?xml version="1.0" encoding="utf-8"?><testsuites name="pytest tests">
<testsuite name="pytest" errors="0" failures="1" skipped="1" tests="4" time="0.1">
<testcase classname="tests.contracts.test_settings" name="test_ok" time="0.001" />
<testcase classname="tests.contracts.test_settings" name="test_bad" time="0.001">
<failure message="assert 1 == 2">trace</failure></testcase>
<testcase classname="tests.evidence.test_snapshots" name="test_skip" time="0.0">
<skipped type="pytest.skip" message="no key">skip</skipped></testcase>
<testcase classname="tests.evidence.test_snapshots" name="test_ok2" time="0.001" />
</testsuite></testsuites>"""

DONE_CHANGES = (
    "`src/episalpha/settings.py`, `tests/contracts/test_settings.py`, `pyproject.toml`, "
    "`src/gone.py:12`"
)
PROGRESS = f"""# M9 progress

| Task | Status | Changes | Verification | Blocker | Next |
|---|---|---|---|---|---|
| M9-T01 | DONE | {DONE_CHANGES} | ok | None | M9-T02 |
| M9-T02 | TODO | Planned: `src/never_built.py` | — | — | M9-T03 |
"""

STATUS = """| # | Task | Title | Status | Depends on | Pack |
|---:|---|---|---|---|---|
| 1 | M9-T01 | One | DONE | — | — |
| 2 | **M9-T02** | Two | **IN_PROGRESS** | M9-T01 | [pack](x.md) |
"""


def test_parse_ruff_json_counts_by_code(diagnose: ModuleType) -> None:
    result = diagnose.parse_ruff_json(RUFF_JSON)
    assert result == {"violations": 3, "by_code": {"E501": 2, "F401": 1}}
    assert diagnose.parse_ruff_json("[]") == {"violations": 0, "by_code": {}}


def test_parse_ruff_json_garbage_is_unknown(diagnose: ModuleType) -> None:
    assert diagnose.parse_ruff_json("error: failed to parse")["violations"] is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Success: no issues found in 20 source files\n", 0),
        ("src/a.py:1: error: x\nFound 3 errors in 2 files (checked 20 source files)\n", 3),
        ("src/a.py:1: error: x\nFound 1 error in 1 file (checked 20 source files)\n", 1),
        ("Traceback (most recent call last):\n  boom\n", None),
    ],
)
def test_parse_mypy(diagnose: ModuleType, text: str, expected: int | None) -> None:
    assert diagnose.parse_mypy(text) == expected


def test_parse_junit_totals_dirs_and_failures(diagnose: ModuleType) -> None:
    result = diagnose.parse_junit(JUNIT)
    assert result["totals"] == {"passed": 2, "failed": 1, "errors": 0, "skipped": 1}
    assert result["by_dir"] == {
        "contracts": {"passed": 1, "failed": 1, "errors": 0, "skipped": 0},
        "evidence": {"passed": 1, "failed": 0, "errors": 0, "skipped": 1},
    }
    assert result["failing"] == ["tests.contracts.test_settings::test_bad"]


def test_parse_junit_garbage_is_unknown(diagnose: ModuleType) -> None:
    assert diagnose.parse_junit("not xml")["totals"] is None


def test_progress_rows(diagnose: ModuleType) -> None:
    rows = diagnose.progress_rows(PROGRESS)
    assert [(row["task"], row["status"]) for row in rows] == [
        ("M9-T01", "DONE"),
        ("M9-T02", "TODO"),
    ]


def test_status_rows_strip_bold(diagnose: ModuleType) -> None:
    assert diagnose.status_rows(STATUS) == {"M9-T01": "DONE", "M9-T02": "IN_PROGRESS"}


def test_missing_files_only_for_done_rows(diagnose: ModuleType, tmp_path: Path) -> None:
    (tmp_path / "src" / "episalpha").mkdir(parents=True)
    (tmp_path / "src" / "episalpha" / "settings.py").write_text("")
    (tmp_path / "tests" / "contracts").mkdir(parents=True)
    (tmp_path / "tests" / "contracts" / "test_settings.py").write_text("")

    missing = diagnose.missing_files(diagnose.progress_rows(PROGRESS), tmp_path)

    # pyproject.toml is not under a tracked prefix; the TODO row is never checked;
    # the line reference is stripped before the existence check.
    assert missing == ["M9-T01: src/gone.py"]


def test_orphan_tests(diagnose: ModuleType, tmp_path: Path) -> None:
    (tmp_path / "tests" / "a").mkdir(parents=True)
    (tmp_path / "tests" / "a" / "test_known.py").write_text("")
    (tmp_path / "tests" / "a" / "test_orphan.py").write_text("")
    (tmp_path / "tests" / "a" / "helper.py").write_text("")

    docs = "Focused test: `tests/a/test_known.py`"
    assert diagnose.orphan_tests(tmp_path, docs) == ["tests/a/test_orphan.py"]


def test_status_mismatches(diagnose: ModuleType) -> None:
    status = {"M9-T01": "DONE", "M9-T02": "IN_PROGRESS"}
    progress = {"M9-T01": "DONE", "M9-T02": "TODO", "M9-T03": "TODO"}
    assert diagnose.status_mismatches(status, progress) == [
        "M9-T02: STATUS=IN_PROGRESS PROGRESS=TODO",
        "M9-T03: STATUS=None PROGRESS=TODO",
    ]


def report(passed: int = 10, failed: int = 0, ruff: int = 0, mypy: int = 0) -> dict[str, Any]:
    return {
        "checks": {
            "ruff": {"violations": ruff, "by_code": {}},
            "format": {"unformatted": []},
            "mypy": {"errors": mypy},
            "pytest": {"passed": passed, "failed": failed, "errors": 0, "skipped": 0},
        },
        "tests": {"by_dir": {}, "failing": []},
        "traceability": {"missing_files": [], "orphan_tests": [], "status_mismatches": []},
    }


def test_no_previous_means_no_regression(diagnose: ModuleType) -> None:
    assert diagnose.regressions(None, report()) == []


def test_seeded_regression_is_detected(diagnose: ModuleType) -> None:
    found = diagnose.regressions(report(passed=12), report(passed=10, failed=1, ruff=2, mypy=1))
    assert any("passed" in item for item in found)
    assert any("failed" in item for item in found)
    assert any("ruff" in item for item in found)
    assert any("mypy" in item for item in found)


def test_new_missing_file_is_a_regression(diagnose: ModuleType) -> None:
    current = report()
    current["traceability"]["missing_files"] = ["M9-T01: src/gone.py"]
    assert diagnose.regressions(report(), current) == ["new missing file: M9-T01: src/gone.py"]


def test_growth_is_not_a_regression(diagnose: ModuleType) -> None:
    assert diagnose.regressions(report(passed=10), report(passed=15)) == []


def test_exit_code(diagnose: ModuleType) -> None:
    green = {**report(), "regressions": []}
    assert diagnose.exit_code(green) == 0

    failing = {**report(failed=1), "regressions": []}
    assert diagnose.exit_code(failing) == 1

    unknown = report()
    unknown["checks"]["mypy"] = {"errors": None}
    assert diagnose.exit_code({**unknown, "regressions": []}) == 1

    regressed = {**report(), "regressions": ["passed tests fell 12 -> 10"]}
    assert diagnose.exit_code(regressed) == 1


def test_render_markdown_sections_in_order(diagnose: ModuleType) -> None:
    text = diagnose.render_markdown(
        {
            **report(failed=1),
            "timestamp": "2026-10-10T00:00:00+00:00",
            "git_head": "abc1234",
            "dirty": True,
            "regressions": [],
        }
    )
    headings = [line for line in text.splitlines() if line.startswith("## ")]
    assert headings == [
        "## Summary",
        "## Checks",
        "## Tests by directory",
        "## Failing tests",
        "## Traceability",
        "## Regressions",
    ]
    assert "FAIL" in text
    assert "abc1234" in text


def test_the_baseline_is_the_last_line_from_the_same_environment(
    diagnose: ModuleType, tmp_path: Path
) -> None:
    # The container skips the compose-config tests, so a host line followed by a container line
    # looked like "passed 637 -> 630": the documented `check` failed after any host run.
    history = tmp_path / "diagnose.jsonl"
    lines = [
        {**report(passed=630), "environment": "container"},
        report(passed=637),  # written before lines carried an environment: the host
        {**report(passed=1), "checks": {}},  # a --no-run line
    ]
    history.write_text("".join(json.dumps(line) + "\n" for line in lines))
    host = diagnose._previous(history, True, "host")
    container = diagnose._previous(history, True, "container")
    assert host is not None and host["checks"]["pytest"]["passed"] == 637
    assert container is not None and container["checks"]["pytest"]["passed"] == 630
    assert diagnose._previous(history, False, "host")["checks"] == {}
