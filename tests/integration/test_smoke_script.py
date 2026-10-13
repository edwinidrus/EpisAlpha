"""M7-T02 — ``scripts/demo_smoke.py``: the whole offline demo in one command, on temporary state.

The script drives the CLI in subprocesses, as a user would. Every run is a fake-runtime FIXTURE.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "demo_smoke.py"


def smoke(tmp: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("EPISALPHA_")}
    env["TMPDIR"] = str(tmp)  # the script's temporary state lands in pytest's directory
    env["EPISALPHA_CONFIG"] = str(REPO / "config" / "does-not-exist.toml")  # must not be read
    return subprocess.run(
        [sys.executable, str(SCRIPT), *arguments],
        capture_output=True,
        text=True,
        env=env,
        cwd=REPO,
        timeout=600,
        check=False,
    )


def test_the_smoke_passes_on_temporary_state_and_prints_where_everything_is(
    tmp_path: Path,
) -> None:
    real = REPO / ".episalpha" / "app.sqlite3"
    before = real.stat().st_mtime_ns if real.exists() else None
    result = smoke(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    out = result.stdout
    assert "[FIXTURE]" in out
    for step in (
        "seed",
        "run supported",
        "run conflicting",
        "run insufficient",
        "replay",
        "export",
        "experiment",
        "backup",
        "restore",
    ):
        assert re.search(rf"^ok {step}\b", out, re.M), (step, out)
    data = re.search(r"^data root: (.+)$", out, re.M)
    vault = re.search(r"^vault: (.+)$", out, re.M)
    report = re.search(r"^report: (.+)$", out, re.M)
    assert data and vault and report, out
    assert not Path(data.group(1)).resolve().is_relative_to(REPO.resolve())
    assert Path(data.group(1)).resolve().is_relative_to(tmp_path.resolve())
    assert Path(report.group(1)).is_file() and Path(vault.group(1)).is_dir()
    assert re.search(r"^replay after warm-up: \d+\.\d+ s$", out, re.M)
    if before is not None:  # the user's own state was never touched
        assert real.stat().st_mtime_ns == before


def test_an_injected_failure_makes_the_smoke_fail(tmp_path: Path) -> None:
    result = smoke(tmp_path, "--inject-failure")
    assert result.returncode != 0
    assert "FAILED" in result.stdout + result.stderr
    assert "INTEGRITY_ERROR" in result.stdout + result.stderr
