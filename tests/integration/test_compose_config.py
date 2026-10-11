"""Portable compose stack (M0-T08, A15), checked through `docker compose config` (no daemon).

Skipped only when the docker compose CLI is absent, e.g. inside the dev container, which has the
docker CLI but not the compose plugin. On the host these always run.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
APP_SERVICES = ("ui", "cli", "setup-worker")


def compose(*files: str, env: dict[str, str] | None = None) -> dict[str, Any]:
    if shutil.which("docker") is None:
        pytest.skip("docker CLI not installed")
    version = subprocess.run(
        ["docker", "compose", "version"],
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": "/tmp", **(env or {})},
    )
    if version.returncode != 0:
        pytest.skip("docker compose plugin not installed")
    argv = ["docker", "compose", "--profile", "tools"]
    for name in files:
        argv += ["-f", str(REPO / name)]
    done = subprocess.run(
        # --no-env-resolution: never merge .env values into the output (no secret can reach a
        # failure message).
        [*argv, "config", "--no-env-resolution", "--format", "json"],
        cwd=REPO,
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": "/tmp", **(env or {})},
        check=False,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)  # type: ignore[no-any-return]


def test_only_the_anchor_publishes_ports_and_only_on_loopback() -> None:
    services = compose("compose.yaml")["services"]
    published = {
        name: [(p["host_ip"], p["published"], p["target"]) for p in svc.get("ports", [])]
        for name, svc in services.items()
        if svc.get("ports")
    }
    assert published == {
        "net": [("127.0.0.1", "8501", 8501), ("127.0.0.1", "6006", 6006)],
    }


def test_anchor_host_ports_are_overridable() -> None:
    services = compose(
        "compose.yaml", env={"EPISALPHA_UI_PORT": "18501", "EPISALPHA_PHOENIX_PORT": "16006"}
    )["services"]
    published = {
        name: [(p["host_ip"], p["published"], p["target"]) for p in svc.get("ports", [])]
        for name, svc in services.items()
        if svc.get("ports")
    }
    assert published == {
        "net": [("127.0.0.1", "18501", 8501), ("127.0.0.1", "16006", 6006)],
    }


def test_app_services_and_phoenix_share_the_anchor_namespace() -> None:
    services = compose("compose.yaml")["services"]
    for name in (*APP_SERVICES, "phoenix"):
        assert services[name]["network_mode"] == "service:net", name
    assert all(svc.get("network_mode") != "host" for svc in services.values())
    assert set(services["net"]["networks"]) == {"app"}
    assert compose("compose.yaml")["networks"]["app"]["name"] == "episalpha-app"


def test_mounts_are_portable_and_never_expose_the_socket_by_default() -> None:
    config = compose("compose.yaml")
    assert config["volumes"]["stages"]["name"] == "episalpha-stages"
    for name in APP_SERVICES:
        service = config["services"][name]
        targets = {v["target"]: v for v in service["volumes"]}
        assert targets["/app/.episalpha"]["type"] == "bind"
        assert targets["/stages"]["source"] == "stages"
        assert targets["/app/config"].get("read_only", False) is (name != "setup-worker")
        assert all(v["source"] != v["target"] for v in service["volumes"])  # no same-path mount
        assert not any("docker.sock" in str(v.get("source")) for v in service["volumes"])
        assert service["working_dir"] == "/app"
        assert service["environment"]["EPISALPHA_SANDBOX_TOPOLOGY"] == "compose"


def test_the_live_override_adds_the_socket_to_app_services_only() -> None:
    services = compose("compose.yaml", "compose.live.yaml")["services"]
    for name in APP_SERVICES:
        assert any("docker.sock" in str(v.get("source")) for v in services[name]["volumes"])
    for name in ("net", "phoenix"):
        volumes = services[name].get("volumes", [])
        assert not any("docker.sock" in str(v.get("source")) for v in volumes), name


def test_services_run_as_the_configured_host_user() -> None:
    env = {"EPISALPHA_UID": "1234", "EPISALPHA_GID": "5678"}
    services = compose("compose.yaml", "compose.dev.yaml", env=env)["services"]
    for name in (*APP_SERVICES, "phoenix", "check"):
        assert services[name]["user"] == "1234:5678", name


def test_dev_override_checks_the_working_copy_offline() -> None:
    services = compose("compose.yaml", "compose.dev.yaml")["services"]
    check = services["check"]
    assert check["network_mode"] == "none"
    assert {v["target"] for v in check["volumes"]} >= {"/app"}
    assert check["environment"]["PYTHONPATH"] == "/app/src"
    assert check["image"] == "episalpha-app:dev"


def test_init_prepares_data_before_the_stack_starts() -> None:
    services = compose("compose.yaml")["services"]
    init = services["init"]
    assert init["user"] == "0:0"
    assert init["network_mode"] == "none"
    assert init["cap_drop"] == ["ALL"]
    assert set(init["cap_add"]) == {"CHOWN", "DAC_OVERRIDE", "FOWNER"}
    assert [volume["target"] for volume in init["volumes"]] == ["/data"]
    assert not init.get("profiles")
    assert not init.get("ports")
    for name in ("net", "phoenix", *APP_SERVICES):
        assert services[name]["depends_on"]["init"]["condition"] == "service_completed_successfully"
