"""M3-T04 — the sandbox's docker invocations, checked offline (no Docker needed).

The live boundary is proven in ``tests/integration/test_runtime_boundary.py``; these tests pin
what the code asks Docker to do, so a later edit cannot quietly add a dangerous mount or flag.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from episalpha.runtime.sandbox import (
    COMPOSE_STAGE_ROOT,
    SandboxConfig,
    SandboxLauncher,
    forwarder_command,
    network_create_command,
    preflight,
    sandbox_config,
    worker_command,
)

IMAGE = "sha256:" + "a" * 64
REPO = Path(__file__).resolve().parents[2]


def config(**overrides: object) -> SandboxConfig:
    return SandboxConfig(image=IMAGE, **overrides)  # type: ignore[arg-type]


def flag_value(argv: Sequence[str], flag: str) -> list[str]:
    return [argv[i + 1] for i, item in enumerate(argv) if item == flag]


def test_image_must_be_pinned() -> None:
    with pytest.raises(ValueError, match="pinned"):
        SandboxConfig(image="episalpha-worker:latest")
    SandboxConfig(image="registry.example/worker@sha256:" + "b" * 64)


def test_worker_network_has_no_host_address() -> None:
    argv = network_create_command(config())
    assert "--internal" in argv
    assert "com.docker.network.bridge.inhibit_ipv4=true" in argv


def test_worker_container_is_hardened(tmp_path: Path) -> None:
    spec, out = tmp_path / "spec.json", tmp_path / "out"
    argv = worker_command(config(), "w1", spec, out, ["python", "-c", "pass"])
    assert flag_value(argv, "--network") == ["episalpha-worker"]
    assert flag_value(argv, "--dns") == ["127.0.0.1"]
    assert "--read-only" in argv
    assert flag_value(argv, "--cap-drop") == ["ALL"]
    assert flag_value(argv, "--security-opt") == ["no-new-privileges:true"]
    assert flag_value(argv, "--user") == ["10001:10001"]
    assert flag_value(argv, "--pids-limit") == ["128"]
    assert flag_value(argv, "--memory") == ["1g"]
    assert all("size=64m" in value for value in flag_value(argv, "--tmpfs"))
    mounts = flag_value(argv, "--mount")
    assert mounts == [
        f"type=bind,src={spec},dst=/run/episalpha/spec.json,readonly",
        f"type=bind,src={out},dst=/run/episalpha/out",
    ]
    assert flag_value(argv, "--env") == ["HERMES_HOME=/home/worker", "HOME=/home/worker"]


def test_nothing_forbidden_reaches_the_worker(tmp_path: Path) -> None:
    argv = " ".join(
        worker_command(
            config(skills_dir=tmp_path / "skills"),
            "w1",
            tmp_path / "spec.json",
            tmp_path / "out",
            ["python"],
        )
    )
    for forbidden in (
        "docker.sock",
        "--privileged",
        "--network host",
        "network=host",
        ".env",
        "app.sqlite3",
        "labels",
        str(REPO) + ",",
        "openrouter_api_key",
        "api_key",
        "/mnt/c",
    ):
        assert forbidden not in argv, forbidden
    assert f"src={tmp_path / 'skills'},dst=/opt/skills,readonly" in argv


def test_forwarder_targets_are_fixed() -> None:
    argv = forwarder_command(config(), "f1", 41234, 41235)
    assert flag_value(argv, "--network") == ["bridge"]
    assert argv[-2:] == ["8080=172.17.0.1:41234", "8081=172.17.0.1:41235"]
    assert "--read-only" in argv
    assert flag_value(argv, "--cap-drop") == ["ALL"]


def test_urls_point_at_the_forwarder_only() -> None:
    launcher = SandboxLauncher(config())
    assert launcher.relay_url(41234) == "http://172.31.252.2:8080/v1"
    assert launcher.mcp_url(41235) == "http://172.31.252.2:8081/mcp"
    assert launcher.bind_host == "172.17.0.1"


class FakeDocker:
    """Records docker calls; ``stop``/``kill`` end the spawned stand-in, as Docker would."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.spawned: subprocess.Popen[bytes] | None = None

    def __call__(self, argv: Sequence[str]) -> subprocess.CompletedProcess[str]:
        self.calls.append(list(argv))
        if argv[1] in ("stop", "kill") and self.spawned is not None:
            self.spawned.kill()
        return subprocess.CompletedProcess(list(argv), 0, "", "")

    def spawn(self, argv: Sequence[str]) -> subprocess.Popen[bytes]:
        sleeper = [sys.executable, "-c", "import time; time.sleep(30)"]
        self.spawned = subprocess.Popen(sleeper)
        return self.spawned


def test_timeout_stops_the_worker_and_removes_the_forwarder(tmp_path: Path) -> None:
    docker = FakeDocker()
    launcher = SandboxLauncher(config(), runner=docker, spawner=docker.spawn)
    stage = tmp_path / "researching"
    (stage / "out").mkdir(parents=True)
    outcome = launcher.launch(
        stage_dir=stage,
        spec_path=stage / "spec.json",
        result_path=stage / "out" / "result.json",
        relay_port=41234,
        mcp_port=41235,
        timeout=1.0,
        extra_env={},
    )
    verbs = [call[1:3] for call in docker.calls]
    assert ["network", "inspect"] in verbs
    assert ["run", "-d"] in verbs
    assert ["network", "connect"] in verbs
    assert ["stop", "-t"] in verbs
    assert docker.calls[-1][1:3] == ["rm", "-f"]
    assert outcome.timed_out
    assert outcome.stop_seconds is not None
    assert outcome.seconds < 10


# --- the compose topology (A15) ---------------------------------------------------------------


def compose() -> SandboxConfig:
    return config(topology="compose")


def test_topology_comes_from_the_environment() -> None:
    assert sandbox_config(IMAGE, {}).topology == "host"
    assert sandbox_config(IMAGE, {"EPISALPHA_SANDBOX_TOPOLOGY": "compose"}).topology == "compose"
    with pytest.raises(ValueError, match="EPISALPHA_SANDBOX_TOPOLOGY"):
        sandbox_config(IMAGE, {"EPISALPHA_SANDBOX_TOPOLOGY": "desktop"})


def test_compose_forwarder_reaches_the_app_by_name_on_the_app_network() -> None:
    argv = forwarder_command(compose(), "f1", 41234, 41235)
    assert flag_value(argv, "--network") == ["episalpha-app"]
    assert argv[-2:] == ["8080=net:41234", "8081=net:41235"]
    assert "--read-only" in argv and flag_value(argv, "--cap-drop") == ["ALL"]


def test_compose_worker_mounts_only_its_stage_sub_paths() -> None:
    stage = COMPOSE_STAGE_ROOT / "run-0123456789ab" / "researching"
    argv = worker_command(
        compose(), "w1", stage / "spec.json", stage / "out", ["python", "-c", "pass"]
    )
    assert flag_value(argv, "--mount") == [
        "type=volume,src=episalpha-stages,dst=/run/episalpha/spec.json,"
        "volume-subpath=run-0123456789ab/researching/spec.json,readonly",
        "type=volume,src=episalpha-stages,dst=/run/episalpha/out,"
        "volume-subpath=run-0123456789ab/researching/out",
    ]
    joined = " ".join(argv)
    assert "type=bind" not in joined and "docker.sock" not in joined
    assert flag_value(argv, "--network") == ["episalpha-worker"]
    assert flag_value(argv, "--dns") == ["127.0.0.1"]


def test_compose_hardening_is_identical_to_host(tmp_path: Path) -> None:
    stage = COMPOSE_STAGE_ROOT / "r" / "s"

    def hardening(argv: list[str]) -> list[str]:
        cut = argv.index("--mount")
        return [a for a in argv[:cut] if a not in ("w1",)]

    host = worker_command(config(), "w1", tmp_path / "spec.json", tmp_path / "out", ["x"])
    other = worker_command(compose(), "w1", stage / "spec.json", stage / "out", ["x"])
    assert hardening(host) == hardening(other)


def test_compose_refuses_stage_paths_outside_the_volume(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        worker_command(compose(), "w1", tmp_path / "spec.json", tmp_path / "out", ["x"])


def test_compose_refuses_volume_root_and_parent_traversal_mounts() -> None:
    stage = COMPOSE_STAGE_ROOT / "run"
    for path in (COMPOSE_STAGE_ROOT, stage / ".." / "x"):
        for spec, out in ((path, stage / "out"), (stage / "spec.json", path)):
            with pytest.raises(ValueError) as error:
                worker_command(compose(), "w1", spec, out, ["x"])
            assert str(path) in str(error.value)


def test_compose_has_no_skills_mount_yet() -> None:
    with pytest.raises(ValueError, match="skills"):
        SandboxConfig(image=IMAGE, topology="compose", skills_dir=Path("/opt/skills"))


def test_compose_binds_inside_the_namespace_and_keeps_forwarder_urls() -> None:
    launcher = SandboxLauncher(compose())
    assert launcher.bind_host == "0.0.0.0"
    assert launcher.relay_url(41234) == "http://172.31.252.2:8080/v1"
    assert compose().stage_root == COMPOSE_STAGE_ROOT
    assert config().stage_root is None and config().bind_host == "172.17.0.1"


def answers(**codes: tuple[int, str]) -> Any:
    """A runner whose reply depends on the docker verb: version, volume, network."""

    def run(argv: Sequence[str]) -> subprocess.CompletedProcess[str]:
        code, out = codes.get(argv[1], (0, ""))
        return subprocess.CompletedProcess(list(argv), code, out, "")

    return run


def test_preflight_passes_on_a_ready_compose_engine() -> None:
    assert preflight(compose(), answers(version=(0, "1.52\n"))) is None
    assert preflight(config(), answers(version=(1, ""))) is None  # host: never checked here


def test_preflight_explains_each_missing_piece() -> None:
    unreachable = preflight(compose(), answers(version=(1, "")))
    assert unreachable is not None and "compose.live.yaml" in unreachable
    old = preflight(compose(), answers(version=(0, "1.44")))
    assert old is not None and "1.45" in old and "26" in old
    garbled = preflight(compose(), answers(version=(0, "banana")))
    assert garbled is not None and "banana" in garbled
    no_volume = preflight(compose(), answers(version=(0, "1.52"), volume=(1, "")))
    assert no_volume is not None and "episalpha-stages" in no_volume
    no_network = preflight(compose(), answers(version=(0, "1.52"), network=(1, "")))
    assert no_network is not None and "episalpha-app" in no_network
