"""Real fake-runtime runs in a ``tmp_path`` workbench, shared by the M5 knowledge tests.

Every run here is a labelled fixture from the fake runtime, never evidence of a live run.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fixtures.run_knowledge import NOW

from episalpha.contracts.research import RuntimeMode
from episalpha.research import services
from episalpha.settings import load_settings

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def config(tmp_path: Path) -> Path:
    path = tmp_path / "test.toml"
    path.write_text(f'[paths]\nproject_root = "{REPO}"\ndata_root = "{tmp_path / "data"}"\n')
    return path


@pytest.fixture
def workbench(config: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[services.Workbench]:
    monkeypatch.setenv("EPISALPHA_FAKE_SCENARIO", "completion")
    opened = services.open_workbench(load_settings(config))
    services.seed_demo(opened)
    yield opened
    opened.close()


@pytest.fixture
def fake_run(workbench: services.Workbench) -> Callable[[str], str]:
    """Admit and execute one completed fake run; the nonce keeps each run distinct."""

    def run(nonce: str) -> str:
        request, plan = services.plan_case(
            workbench, "supported", RuntimeMode.FAKE, now=NOW, nonce=nonce
        )
        services.submit(workbench, request, plan)
        services.execute(workbench, request.run_id, worker_id="test", now=lambda: NOW)
        return request.run_id

    return run
