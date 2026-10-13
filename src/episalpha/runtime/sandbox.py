"""Whole-worker isolation for the Hermes stage worker (plan M3-T04; amendments A12, A15).

The worker runs in a container that can reach exactly two endpoints: the model relay and the
stage's MCP tool server, on the host or in the compose app namespace. How:

- **Worker network.** An ``--internal`` bridge created with
  ``com.docker.network.bridge.inhibit_ipv4=true``, so the host has *no address* on it. A plain
  internal network still lets a container reach every host service bound to ``0.0.0.0`` through
  its gateway IP (observed on this host: ports 8000 and 8080). Without a host address there is
  nothing to reach but the other members of the network. Both topologies use this worker network.
- **Forwarder.** The network's only other member: a container that forwards two fixed ports to
  the relay and the MCP server. On the host it uses the docker0 gateway; in compose it reaches
  the ``net`` anchor by name on ``episalpha-app``. It carries no routing logic the worker could
  steer.
- **DNS.** ``--dns 127.0.0.1``: nothing resolves, so DNS cannot carry data out
  (the CVE-2024-29018 class).
- **Hardening.** Image by digest (a local build's content ID), non-root user, read-only root
  filesystem, size-capped tmpfs for ``/tmp`` and ``HERMES_HOME``, all capabilities dropped,
  ``no-new-privileges``, the default seccomp profile, and pids, memory and CPU limits.
- **Mounts.** The stage spec read-only, promoted skills read-only (empty in v0.1), and one
  per-stage output directory read-write. Host topology uses bind mounts; compose uses only the
  stage's sub-paths in ``episalpha-stages`` and rejects promoted skills for now. Never the
  repository, the canonical database, labels, the Docker socket or ``.env``; the provider key
  never enters the container.
- **Watchdog.** The parent enforces the wall-time deadline with ``docker stop`` (short grace)
  and then ``docker kill``, and measures how long stopping took.

Host-engine decision (owner, 2026-10-10): the current rootful Docker Engine is hardened as
above; rootless Docker or userns-remap stays an owner TODO, so a container escape would still
land as root in the WSL distro.
"""

from __future__ import annotations

import shutil
import subprocess
import tarfile
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

WORKER_UID = 10001
CONTAINER_SPEC = "/run/episalpha/spec.json"
CONTAINER_OUT = "/run/episalpha/out"
CONTAINER_SKILLS = "/opt/skills"
CONTAINER_HOME = "/home/worker"
WORKER_PYTHON = "/opt/hermes/.venv/bin/python"
WORKER_SCRIPT = "/opt/episalpha/hermes_stage.py"
FORWARDER_SCRIPT = "/opt/episalpha/forwarder.py"

Topology = Literal["host", "compose"]
TOPOLOGY_ENV = "EPISALPHA_SANDBOX_TOPOLOGY"
COMPOSE_APP_NETWORK = "episalpha-app"
COMPOSE_RELAY_HOST = "net"
COMPOSE_STAGE_VOLUME = "episalpha-stages"
COMPOSE_STAGE_ROOT = Path("/stages")
MIN_DOCKER_API = (1, 45)
"""``volume-subpath`` mounts need Docker Engine API 1.45 (Engine 26)."""

Runner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]
Spawner = Callable[[Sequence[str]], "subprocess.Popen[bytes]"]


def _docker(arguments: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(arguments), capture_output=True, text=True, check=False)


PROBE_SECONDS = 15
"""ponytail: an operational probe timeout like the 30 s stop wait below, not a research budget."""


def _probe(arguments: Sequence[str]) -> subprocess.CompletedProcess[str]:
    """A quick Docker query for :func:`preflight`, which runs on the submit path: a daemon that
    never answers reads as a failed call, not a hang. Builds and stops keep :func:`_docker`."""
    try:
        return subprocess.run(
            list(arguments), capture_output=True, text=True, check=False, timeout=PROBE_SECONDS
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(list(arguments), 124, "", "no answer in time")


def _spawn(arguments: Sequence[str]) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        list(arguments),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


@dataclass(frozen=True)
class SandboxConfig:
    image: str
    """The worker image by content ID or digest (``sha256:...``), never by tag."""
    topology: Topology = "host"
    network: str = "episalpha-worker"
    subnet: str = "172.31.252.0/24"
    forwarder_ip: str = "172.31.252.2"
    host_gateway: str = "172.17.0.1"
    relay_listen: int = 8080
    mcp_listen: int = 8081
    memory: str = "1g"
    cpus: str = "1.0"
    pids_limit: int = 128
    tmpfs_mb: int = 64
    stop_grace_seconds: int = 2
    skills_dir: Path | None = None
    docker: str = "docker"

    def __post_init__(self) -> None:
        if not self.image.startswith("sha256:") and "@sha256:" not in self.image:
            raise ValueError(f"worker image {self.image!r} must be pinned by digest or ID")
        if self.topology == "compose" and self.skills_dir is not None:
            raise ValueError("promoted skills are not mounted in the compose topology yet (M8)")

    @property
    def forward_target(self) -> str:
        """Where the forwarder sends worker traffic: the anchor by name, or the host gateway."""
        return COMPOSE_RELAY_HOST if self.topology == "compose" else self.host_gateway

    @property
    def forwarder_network(self) -> str:
        return COMPOSE_APP_NETWORK if self.topology == "compose" else "bridge"

    @property
    def bind_host(self) -> str:
        """Where the relay and MCP server listen. In compose: every interface of the shared
        namespace, reachable only from episalpha-app (the forwarder), never published.
        """
        return "0.0.0.0" if self.topology == "compose" else self.host_gateway

    @property
    def stage_root(self) -> Path | None:
        """The stage volume's mount point in compose; ``None`` means host bind mounts."""
        return COMPOSE_STAGE_ROOT if self.topology == "compose" else None


def sandbox_config(image: str, environ: Mapping[str, str]) -> SandboxConfig:
    """The launcher configuration for this process: ``host`` unless compose says otherwise."""
    topology = environ.get(TOPOLOGY_ENV) or "host"
    if topology == "compose":
        return SandboxConfig(image=image, topology="compose")
    if topology == "host":
        return SandboxConfig(image=image)
    raise ValueError(f"{TOPOLOGY_ENV}={topology!r}: expected 'host' or 'compose'")


def _mount(config: SandboxConfig, source: Path, target: str, *, readonly: bool) -> str:
    suffix = ",readonly" if readonly else ""
    if config.stage_root is None:
        return f"type=bind,src={source},dst={target}{suffix}"
    sub_path = source.relative_to(config.stage_root).as_posix()  # ValueError outside the volume
    if sub_path == "." or ".." in Path(sub_path).parts:
        raise ValueError(f"unsafe stage sub-path: {source}")
    return f"type=volume,src={COMPOSE_STAGE_VOLUME},dst={target},volume-subpath={sub_path}{suffix}"


def preflight(config: SandboxConfig, runner: Runner = _probe) -> str | None:
    """Why the compose topology cannot run a worker here, or ``None``. Host topology: ``None``."""
    if config.topology != "compose":
        return None
    version = runner([config.docker, "version", "--format", "{{.Server.APIVersion}}"])
    if version.returncode != 0:
        return (
            "the Docker engine is unreachable from this container; live runs need the socket "
            "from compose.live.yaml"
        )
    text = version.stdout.strip()
    try:
        api = tuple(int(part) for part in text.split(".")[:2])
    except ValueError:
        return f"unrecognised Docker Engine API version {text!r}"
    if api < MIN_DOCKER_API:
        return (
            f"Docker Engine API {text} has no volume sub-paths; live runs need API 1.45+ "
            "(Docker Engine 26+)"
        )
    for kind, name in (("volume", COMPOSE_STAGE_VOLUME), ("network", COMPOSE_APP_NETWORK)):
        if runner([config.docker, kind, "inspect", name]).returncode != 0:
            return f"Docker {kind} {name!r} is missing; start the stack with `docker compose up -d`"
    return None


def _hardening(config: SandboxConfig, *, pids: int, memory: str) -> list[str]:
    return [
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--pids-limit",
        str(pids),
        "--memory",
        memory,
        "--cpus",
        config.cpus,
        "--user",
        f"{WORKER_UID}:{WORKER_UID}",
        "--tmpfs",
        f"/tmp:rw,nosuid,nodev,size={config.tmpfs_mb}m",
    ]


def network_create_command(config: SandboxConfig) -> list[str]:
    return [
        config.docker,
        "network",
        "create",
        "--internal",
        "--subnet",
        config.subnet,
        "-o",
        "com.docker.network.bridge.inhibit_ipv4=true",
        config.network,
    ]


def forwarder_command(
    config: SandboxConfig, name: str, relay_port: int, mcp_port: int
) -> list[str]:
    return [
        config.docker,
        "run",
        "-d",
        "--rm",
        "--name",
        name,
        "--network",
        config.forwarder_network,
        *_hardening(config, pids=32, memory="128m"),
        config.image,
        WORKER_PYTHON,
        FORWARDER_SCRIPT,
        f"{config.relay_listen}={config.forward_target}:{relay_port}",
        f"{config.mcp_listen}={config.forward_target}:{mcp_port}",
    ]


def worker_command(
    config: SandboxConfig, name: str, spec_path: Path, out_dir: Path, command: Sequence[str]
) -> list[str]:
    mounts = [
        "--mount",
        _mount(config, spec_path, CONTAINER_SPEC, readonly=True),
        "--mount",
        _mount(config, out_dir, CONTAINER_OUT, readonly=False),
    ]
    if config.skills_dir is not None:
        mounts += ["--mount", f"type=bind,src={config.skills_dir},dst={CONTAINER_SKILLS},readonly"]
    return [
        config.docker,
        "run",
        "--rm",
        "--name",
        name,
        "--network",
        config.network,
        "--dns",
        "127.0.0.1",
        *_hardening(config, pids=config.pids_limit, memory=config.memory),
        "--tmpfs",
        f"{CONTAINER_HOME}:rw,nosuid,nodev,size={config.tmpfs_mb}m,uid={WORKER_UID},gid={WORKER_UID}",
        "--env",
        f"HERMES_HOME={CONTAINER_HOME}",
        "--env",
        f"HOME={CONTAINER_HOME}",
        *mounts,
        config.image,
        *command,
    ]


@dataclass
class LaunchOutcome:
    exit_code: int | None
    timed_out: bool
    cancelled: bool
    seconds: float
    stop_seconds: float | None = None
    home_report: dict[str, Any] = field(default_factory=dict)


class SandboxLauncher:
    """Runs the stage worker in the hardened container, behind the forwarder."""

    def __init__(
        self, config: SandboxConfig, *, runner: Runner = _docker, spawner: Spawner = _spawn
    ) -> None:
        self.config = config
        self._run = runner
        self._spawn = spawner
        self._worker: str | None = None
        self._cancelled = False
        self.bind_host = config.bind_host

    def relay_url(self, relay_port: int) -> str:
        return f"http://{self.config.forwarder_ip}:{self.config.relay_listen}/v1"

    def mcp_url(self, mcp_port: int) -> str:
        return f"http://{self.config.forwarder_ip}:{self.config.mcp_listen}/mcp"

    def ensure_network(self) -> None:
        exists = self._run([self.config.docker, "network", "inspect", self.config.network])
        if exists.returncode != 0:
            created = self._run(network_create_command(self.config))
            if created.returncode != 0:
                raise RuntimeError(f"cannot create worker network: {created.stderr.strip()}")

    def launch(
        self,
        *,
        stage_dir: Path,
        spec_path: Path,
        result_path: Path,
        relay_port: int,
        mcp_port: int,
        timeout: float,
        extra_env: Mapping[str, str],
        command: Sequence[str] | None = None,
    ) -> LaunchOutcome:
        self.ensure_network()
        suffix = stage_dir.name.replace("_", "-")[:20]
        token = f"{int(time.time() * 1000) % 10**9}"
        forwarder = f"episalpha-fwd-{suffix}-{token}"
        worker = f"episalpha-worker-{suffix}-{token}"
        started = time.monotonic()
        stop_seconds: float | None = None
        timed_out = False
        try:
            forwarded = self._run(forwarder_command(self.config, forwarder, relay_port, mcp_port))
            if forwarded.returncode != 0:
                raise RuntimeError(f"forwarder did not start: {forwarded.stderr.strip()}")
            connected = self._run(
                [
                    self.config.docker,
                    "network",
                    "connect",
                    "--ip",
                    self.config.forwarder_ip,
                    self.config.network,
                    forwarder,
                ]
            )
            if connected.returncode != 0:
                raise RuntimeError(f"forwarder not on worker network: {connected.stderr.strip()}")
            argv = worker_command(
                self.config,
                worker,
                spec_path,
                result_path.parent,
                command
                or [
                    WORKER_PYTHON,
                    WORKER_SCRIPT,
                    CONTAINER_SPEC,
                    f"{CONTAINER_OUT}/{result_path.name}",
                ],
            )
            self._worker = worker
            self.last_command = argv
            process = self._spawn(argv)
            try:
                exit_code: int | None = process.wait(timeout=max(1.0, timeout))
            except subprocess.TimeoutExpired:
                timed_out = True
                stop_seconds = self.stop(worker)
                exit_code = process.wait(timeout=30)
            if self._cancelled and stop_seconds is None:
                stop_seconds = self.last_stop_seconds
        finally:
            self._worker = None
            self._run([self.config.docker, "rm", "-f", forwarder])
        return LaunchOutcome(
            exit_code=exit_code,
            timed_out=timed_out,
            cancelled=self._cancelled,
            seconds=round(time.monotonic() - started, 2),
            stop_seconds=stop_seconds,
        )

    last_stop_seconds: float | None = None
    last_command: list[str] | None = None

    def stop(self, name: str) -> float:
        """``docker stop`` with a short grace, then ``docker kill``. Returns the seconds taken."""
        started = time.monotonic()
        stopped = self._run(
            [self.config.docker, "stop", "-t", str(self.config.stop_grace_seconds), name]
        )
        if stopped.returncode != 0:
            self._run([self.config.docker, "kill", name])
        self.last_stop_seconds = round(time.monotonic() - started, 2)
        return self.last_stop_seconds

    def cancel(self) -> None:
        self._cancelled = True
        if self._worker is not None:
            self.stop(self._worker)


# --- the image -------------------------------------------------------------------------------


def build_image(
    *,
    hermes_source: Path,
    commit: str,
    repo_root: Path,
    tag: str = "episalpha-worker:local",
    runner: Runner = _docker,
) -> str:
    """Build the worker image from a minimal context; returns its content ID (``sha256:...``).

    The context holds only a ``git archive`` of the pinned Hermes commit, the stage worker, the
    forwarder and the Dockerfile.
    """
    with tempfile.TemporaryDirectory(prefix="episalpha-worker-build-") as scratch:
        context = Path(scratch)
        archive = context / "hermes.tar"
        with archive.open("wb") as handle:
            produced = subprocess.run(
                ["git", "-C", str(hermes_source), "archive", "--format=tar", commit],
                stdout=handle,
                check=False,
            )
        if produced.returncode != 0:
            raise RuntimeError(f"git archive of {commit} failed")
        target = context / "hermes-agent"
        target.mkdir()
        with tarfile.open(archive) as bundle:
            bundle.extractall(target, filter="data")
        archive.unlink()
        shutil.copy(repo_root / "worker" / "hermes_stage.py", context / "hermes_stage.py")
        shutil.copy(repo_root / "container" / "forwarder.py", context / "forwarder.py")
        shutil.copy(repo_root / "container" / "Dockerfile", context / "Dockerfile")
        built = runner(["docker", "build", "-t", tag, str(context)])
        if built.returncode != 0:
            raise RuntimeError(f"docker build failed: {built.stderr[-2000:]}")
    inspected = runner(["docker", "image", "inspect", "--format", "{{.Id}}", tag])
    return inspected.stdout.strip()
