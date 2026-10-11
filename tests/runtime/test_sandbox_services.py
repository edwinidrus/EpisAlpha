"""A15: in the compose topology a Hermes run that cannot start is refused before admission."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from episalpha.contracts.errors import EpisAlphaError
from episalpha.research import services
from episalpha.runtime import sandbox
from episalpha.settings import load_settings

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def workbench(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> services.Workbench:
    monkeypatch.setenv("EPISALPHA_TEST_KEY", "sk-sentinel-never-printed")
    monkeypatch.delenv("EPISALPHA_WORKER", raising=False)
    path = tmp_path / "test.toml"
    path.write_text(
        f'[paths]\nproject_root = "{REPO}"\ndata_root = "{tmp_path / "data"}"\n\n'
        '[provider]\nmodel_id = "vendor/model:free"\n'
        'endpoint_url = "https://openrouter.ai/api/v1"\napi_key_env = "ENV:EPISALPHA_TEST_KEY"\n'
    )
    return services.open_workbench(load_settings(path))


def test_compose_without_the_socket_is_refused_before_admission(
    workbench: services.Workbench, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EPISALPHA_SANDBOX_TOPOLOGY", "compose")
    monkeypatch.setattr(services.shutil, "which", lambda name: "/usr/local/bin/docker")
    monkeypatch.setattr(
        sandbox,
        "_docker",
        lambda argv: __import__("subprocess").CompletedProcess(list(argv), 1, "", "no socket"),
    )
    with pytest.raises(EpisAlphaError, match="compose.live.yaml"):
        services._hermes_readiness(workbench)
    workbench.close()


def test_an_unknown_topology_is_refused_cleanly(
    workbench: services.Workbench, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EPISALPHA_SANDBOX_TOPOLOGY", "desktop")
    monkeypatch.setattr(services.shutil, "which", lambda name: "/usr/local/bin/docker")
    with pytest.raises(EpisAlphaError, match="EPISALPHA_SANDBOX_TOPOLOGY"):
        services._hermes_readiness(workbench)
    workbench.close()


def test_the_lock_names_a_worker_image() -> None:
    lock = json.loads((REPO / "config" / "runtime.lock.json").read_text())
    assert lock["hermes"]["worker_image"]["id"].startswith("sha256:")
