#!/usr/bin/env python3
"""Implementation diagnostics for EpisAlpha (M0-T05, amendment A11).

One command gives a white-box health picture of the build::

    uv run python scripts/diagnose.py            # the four checks plus traceability
    uv run python scripts/diagnose.py --no-run   # traceability only

It rewrites ``implementation/DIAGNOSTICS.md``, appends one JSON line to
``implementation/logs/diagnose.jsonl`` and exits non-zero when a check fails or anything
regressed against the previous line.

It reads and runs checks only. It never edits source or tests (M0 constitution article 7), never
imports ``episalpha`` (it must work when the package is broken) and never reads ``.env``.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ElementTree
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
IMPLEMENTATION = REPO_ROOT / "implementation"
DIAGNOSTICS_MD = IMPLEMENTATION / "DIAGNOSTICS.md"
HISTORY = IMPLEMENTATION / "logs" / "diagnose.jsonl"

TRACKED_PREFIXES = ("src/", "tests/", "scripts/", "config/", "apps/", "docs/")
DONE_STATUSES = ("DONE", "DONE_OFFLINE")
TASK_ROW = re.compile(r"^\|\s*\**(M\d+-T\d+b?)\**\s*\|")
BACKTICKED = re.compile(r"`([^`\s]+)`")


# --- parsers -------------------------------------------------------------------------------


def parse_ruff_json(text: str) -> dict[str, Any]:
    """Violation count by rule code from ``ruff check --output-format=json``."""
    try:
        items = json.loads(text)
    except json.JSONDecodeError:
        return {"violations": None, "by_code": {}}
    codes = Counter(str(item.get("code")) for item in items)
    return {"violations": len(items), "by_code": dict(sorted(codes.items()))}


def parse_mypy(text: str) -> int | None:
    """Error count from mypy's summary line; ``None`` when no summary line exists."""
    if re.search(r"^Success: no issues found", text, re.M):
        return 0
    match = re.search(r"^Found (\d+) errors? in", text, re.M)
    return int(match.group(1)) if match else None


def parse_format_check(text: str) -> list[str]:
    """Files ``ruff format --check`` would reformat."""
    return sorted(
        line.removeprefix("Would reformat:").strip()
        for line in text.splitlines()
        if line.startswith("Would reformat:")
    )


def _empty_counts() -> dict[str, int]:
    return {"passed": 0, "failed": 0, "errors": 0, "skipped": 0}


def parse_junit(xml_text: str) -> dict[str, Any]:
    """Pass/fail/error/skip totals, per ``tests/<dir>`` counts and failing test names."""
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return {"totals": None, "by_dir": {}, "failing": []}
    totals = _empty_counts()
    by_dir: dict[str, dict[str, int]] = {}
    failing: list[str] = []
    for case in root.iter("testcase"):
        classname = case.get("classname", "")
        parts = classname.split(".")
        directory = parts[1] if len(parts) > 2 and parts[0] == "tests" else "(root)"
        if case.find("failure") is not None:
            outcome = "failed"
        elif case.find("error") is not None:
            outcome = "errors"
        elif case.find("skipped") is not None:
            outcome = "skipped"
        else:
            outcome = "passed"
        totals[outcome] += 1
        by_dir.setdefault(directory, _empty_counts())[outcome] += 1
        if outcome in ("failed", "errors"):
            failing.append(f"{classname}::{case.get('name')}")
    return {"totals": totals, "by_dir": dict(sorted(by_dir.items())), "failing": failing}


# --- traceability --------------------------------------------------------------------------


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in re.split(r"(?<!\\)\|", line.strip().strip("|"))]


def progress_rows(markdown: str) -> list[dict[str, str]]:
    """Task rows of a phase ``PROGRESS.md`` table: Task | Status | Changes | ..."""
    rows = []
    for line in markdown.splitlines():
        if TASK_ROW.match(line):
            cells = _cells(line)
            if len(cells) >= 3:
                task, status, changes = cells[0].strip("*"), cells[1].strip("*"), cells[2]
                rows.append({"task": task, "status": status, "changes": changes})
    return rows


def status_rows(markdown: str) -> dict[str, str]:
    """Task -> status from ``STATUS.md``: # | Task | Title | Status | ..."""
    found = {}
    for line in markdown.splitlines():
        cells = _cells(line)
        if len(cells) >= 4 and re.fullmatch(r"\**M\d+-T\d+b?\**", cells[1]):
            found[cells[1].strip("*")] = cells[3].strip("*")
    return found


def _repo_path(token: str) -> str | None:
    if not token.startswith(TRACKED_PREFIXES) or any(char in token for char in "*<>{}"):
        return None
    path = token.split("::")[0]
    return re.sub(r":\d+(-\d+)?$", "", path).rstrip(".,;")


def missing_files(rows: list[dict[str, str]], root: Path) -> list[str]:
    """Backticked repo paths named by DONE rows that do not exist on disk."""
    missing = []
    for row in rows:
        if row["status"] not in DONE_STATUSES:
            continue
        for token in BACKTICKED.findall(row["changes"]):
            path = _repo_path(token)
            if path is not None and not (root / path).exists():
                missing.append(f"{row['task']}: {path}")
    return missing


def orphan_tests(root: Path, docs_text: str) -> list[str]:
    """Test files no progress row, task pack or journal mentions."""
    orphans = []
    for test in sorted((root / "tests").rglob("test_*.py")):
        relative = test.relative_to(root).as_posix()
        if relative not in docs_text and test.name not in docs_text:
            orphans.append(relative)
    return orphans


def status_mismatches(status: dict[str, str], progress: dict[str, str]) -> list[str]:
    return [
        f"{task}: STATUS={status.get(task)} PROGRESS={progress.get(task)}"
        for task in sorted(status.keys() | progress.keys())
        if status.get(task) != progress.get(task)
    ]


# --- verdict -------------------------------------------------------------------------------


def regressions(previous: dict[str, Any] | None, current: dict[str, Any]) -> list[str]:
    """What got worse since the previous line. Growth is never a regression."""
    if previous is None:
        return []
    found = []
    before, after = previous.get("checks") or {}, current.get("checks") or {}
    if before and after:
        old_tests, new_tests = before["pytest"], after["pytest"]
        if old_tests and new_tests:
            for key, worse in (("passed", -1), ("failed", 1), ("errors", 1)):
                old, new = old_tests[key], new_tests[key]
                if (new - old) * worse > 0:
                    found.append(f"{key} tests {old} -> {new}")
        for name, key in (("ruff", "violations"), ("mypy", "errors")):
            old, new = before[name][key], after[name][key]
            if old is not None and new is not None and new > old:
                found.append(f"{name} {key} {old} -> {new}")
    old_missing = set(previous.get("traceability", {}).get("missing_files", []))
    for item in current["traceability"]["missing_files"]:
        if item not in old_missing:
            found.append(f"new missing file: {item}")
    return found


def failures(report: dict[str, Any]) -> list[str]:
    found = []
    checks = report.get("checks") or {}
    if checks:
        if checks["ruff"]["violations"] != 0:
            found.append(f"ruff violations: {checks['ruff']['violations']}")
        if checks["format"]["unformatted"]:
            found.append(f"unformatted files: {len(checks['format']['unformatted'])}")
        if checks["mypy"]["errors"] != 0:
            found.append(f"mypy errors: {checks['mypy']['errors']}")
        tests = checks["pytest"]
        if tests is None or tests["failed"] or tests["errors"]:
            found.append(f"pytest: {tests}")
    trace = report["traceability"]
    found += [f"missing file {item}" for item in trace["missing_files"]]
    found += [f"status mismatch {item}" for item in trace["status_mismatches"]]
    return found


def exit_code(report: dict[str, Any]) -> int:
    return 1 if failures(report) or report["regressions"] else 0


def render_markdown(report: dict[str, Any]) -> str:
    verdict = "PASS" if exit_code(report) == 0 else "FAIL"
    checks = report.get("checks") or {}
    trace = report["traceability"]
    lines = [
        "# Diagnostics",
        "",
        "Written by `uv run python scripts/diagnose.py`. Do not edit by hand; history is in",
        "`logs/diagnose.jsonl`.",
        "",
        "## Summary",
        "",
        f"- Verdict: **{verdict}**",
        f"- Timestamp: {report['timestamp']}",
        f"- Git HEAD: `{report['git_head']}`{' (dirty working tree)' if report['dirty'] else ''}",
    ]
    lines += [f"- Failure: {item}" for item in failures(report)]
    lines += ["", "## Checks", ""]
    if checks:
        tests, ruff = checks["pytest"], checks["ruff"]
        lines += [
            f"- `ruff check`: {ruff['violations']} violations {ruff['by_code']}",
            f"- `ruff format --check`: {len(checks['format']['unformatted'])} files to reformat",
            f"- `mypy src/episalpha`: {checks['mypy']['errors']} errors",
            f'- `pytest -m "not live"`: {tests}',
        ]
    else:
        lines.append("- Not run (`--no-run`).")
    lines += ["", "## Tests by directory", ""]
    by_dir = report["tests"]["by_dir"]
    if by_dir:
        lines += ["| Directory | Passed | Failed | Errors | Skipped |", "|---|---:|---:|---:|---:|"]
        for name, counts in by_dir.items():
            lines.append(
                f"| {name} | {counts['passed']} | {counts['failed']} | {counts['errors']} "
                f"| {counts['skipped']} |"
            )
    else:
        lines.append("- None recorded.")
    lines += ["", "## Failing tests", ""]
    lines += [f"- `{name}`" for name in report["tests"]["failing"]] or ["- None."]
    lines += ["", "## Traceability", ""]
    for title, key in (
        ("Missing files named by DONE rows", "missing_files"),
        ("Tests no record mentions (orphans)", "orphan_tests"),
        ("STATUS.md vs PROGRESS.md mismatches", "status_mismatches"),
    ):
        lines.append(f"- {title}: {len(trace[key])}")
        lines += [f"  - `{item}`" for item in trace[key]]
    lines += ["", "## Regressions", ""]
    lines += [f"- {item}" for item in report["regressions"]] or ["- None."]
    return "\n".join(lines) + "\n"


# --- wiring --------------------------------------------------------------------------------


def _run(*command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True, check=False)


def run_checks() -> tuple[dict[str, Any], dict[str, Any]]:
    ruff = parse_ruff_json(_run("uv", "run", "ruff", "check", "--output-format=json", ".").stdout)
    format_result = _run("uv", "run", "ruff", "format", "--check", ".")
    mypy = parse_mypy(_run("uv", "run", "mypy", "src/episalpha").stdout)
    with tempfile.TemporaryDirectory() as scratch:
        junit_path = Path(scratch) / "junit.xml"
        _run("uv", "run", "pytest", "-q", "-m", "not live", f"--junitxml={junit_path}")
        junit = parse_junit(junit_path.read_text() if junit_path.exists() else "")
    checks = {
        "ruff": ruff,
        "format": {"unformatted": parse_format_check(format_result.stdout)},
        "mypy": {"errors": mypy},
        "pytest": junit["totals"],
    }
    return checks, {"by_dir": junit["by_dir"], "failing": junit["failing"]}


def traceability(root: Path) -> dict[str, list[str]]:
    implementation = root / "implementation"
    rows: list[dict[str, str]] = []
    for progress in sorted(implementation.glob("M*/PROGRESS.md")):
        rows += progress_rows(progress.read_text())
    docs_text = "\n".join(path.read_text() for path in sorted(implementation.rglob("*.md")))
    status = status_rows((implementation / "STATUS.md").read_text())
    return {
        "missing_files": missing_files(rows, root),
        "orphan_tests": orphan_tests(root, docs_text),
        "status_mismatches": status_mismatches(status, {r["task"]: r["status"] for r in rows}),
    }


def _previous(history: Path, want_checks: bool) -> dict[str, Any] | None:
    if not history.exists():
        return None
    lines = [json.loads(line) for line in history.read_text().splitlines() if line.strip()]
    candidates = [line for line in lines if line.get("checks")] if want_checks else lines
    return candidates[-1] if candidates else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--no-run", action="store_true", help="traceability only")
    arguments = parser.parse_args()

    started = time.monotonic()
    checks, tests = ({}, {"by_dir": {}, "failing": []}) if arguments.no_run else run_checks()
    report: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
        "git_head": _run("git", "rev-parse", "--short", "HEAD").stdout.strip(),
        "dirty": bool(_run("git", "status", "--porcelain").stdout.strip()),
        "mode": "no-run" if arguments.no_run else "full",
        "checks": checks,
        "tests": tests,
        "traceability": traceability(REPO_ROOT),
    }
    report["regressions"] = regressions(_previous(HISTORY, bool(checks)), report)
    report["elapsed_seconds"] = round(time.monotonic() - started, 1)

    DIAGNOSTICS_MD.write_text(render_markdown(report))
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY.open("a") as handle:
        handle.write(json.dumps(report, sort_keys=True) + "\n")

    code = exit_code(report)
    summary = checks.get("pytest") if checks else "not run"
    print(
        f"diagnose: {'PASS' if code == 0 else 'FAIL'} | tests {summary} | "
        f"failures {len(failures(report))} | regressions {len(report['regressions'])} | "
        f"orphans {len(report['traceability']['orphan_tests'])} | {report['elapsed_seconds']}s"
    )
    return code


if __name__ == "__main__":
    sys.exit(main())
