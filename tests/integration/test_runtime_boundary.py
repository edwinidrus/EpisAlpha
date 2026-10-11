"""Live: the worker container's boundary (M3-T04). Needs Docker and the pinned worker image.

    uv run pytest -q -m live tests/integration/test_runtime_boundary.py

No model calls. A probe runs inside the real worker container with the real hardening and
network, tries every forbidden access, and plants a symlink for the host reader.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from episalpha.runtime.hermes import read_worker_json
from episalpha.runtime.sandbox import CONTAINER_OUT, WORKER_PYTHON, SandboxConfig, SandboxLauncher

pytestmark = pytest.mark.live

ROOT = Path(__file__).resolve().parents[2]
LOCK = json.loads((ROOT / "config" / "runtime.lock.json").read_text())
IMAGE = LOCK["hermes"].get("worker_image", {}).get("id", "")
HOST_HOME = str(Path.home())

PROBE = r"""
import json, os, socket, subprocess, urllib.request
REPO, HOME, RELAY_PORT = %r, %r, %d
results = {}

def attempt(name, action):
    try:
        results[name] = "ALLOWED: " + str(action())[:80]
    except BaseException as error:
        results[name] = "BLOCKED: %%s: %%s" %% (type(error).__name__, str(error)[:90])

attempt("see_repository", lambda: os.listdir(REPO))
attempt("open_canonical_db", lambda: open(REPO + "/.episalpha/app.sqlite3", "rb").read(1))
attempt("read_env_file", lambda: open(REPO + "/.env").read(1))
attempt("write_spec", lambda: open("/run/episalpha/spec.json", "a").write("x"))
attempt("write_root_filesystem", lambda: open("/opt/hermes/planted", "w").write("x"))
attempt("write_skills_mount", lambda: open("/opt/skills/new-skill.md", "w").write("x"))
attempt("https_example_com",
        lambda: urllib.request.urlopen("https://example.com", timeout=5).status)
attempt("dns_example_com", lambda: socket.getaddrinfo("example.com", 443))
attempt("list_mnt_c", lambda: os.listdir("/mnt/c"))
attempt("list_host_home", lambda: os.listdir(HOME))
attempt("docker_socket", lambda: os.stat("/var/run/docker.sock"))
for host, port in [("172.31.252.1", 8000), ("172.31.252.1", 8080), ("172.17.0.1", 8000),
                   ("172.17.0.1", RELAY_PORT), ("172.31.252.2", 9999), ("1.1.1.1", 443)]:
    attempt("tcp_%%s_%%d" %% (host, port),
            lambda h=host, p=port: socket.create_connection((h, p), timeout=3).close() or "open")
attempt("relay_via_forwarder",
        lambda: urllib.request.urlopen("http://172.31.252.2:8080/v1/ping", timeout=5).read())

def fork_many():
    children = []
    try:
        for _ in range(400):
            children.append(subprocess.Popen(["sleep", "5"]))
        return "spawned %%d" %% len(children)
    finally:
        for child in children:
            child.kill()

attempt("fork_400_processes", fork_many)

def fill_tmp():
    with open("/tmp/fill", "wb") as handle:
        for _ in range(200):
            handle.write(b"0" * 1048576)
            handle.flush()
    return "wrote 200 MiB"

attempt("fill_tmp_200_mib", fill_tmp)
results["uid"] = os.getuid()
os.symlink("/etc/hostname", "/run/episalpha/out/result.json")
json.dump(results, open("/run/episalpha/out/probe.json", "w"))
"""


@pytest.fixture(scope="module")
def relay_stub() -> Iterator[int]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            body = b"relay-ok"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return None

    server = HTTPServer(("172.17.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield int(server.server_address[1])
    server.shutdown()
    server.server_close()


@pytest.fixture
def launcher(tmp_path: Path) -> SandboxLauncher:
    if not IMAGE or shutil.which("docker") is None:
        pytest.skip("Docker or the pinned worker image is not available")
    skills = tmp_path / "skills"
    skills.mkdir()
    (skills / "promoted.md").write_text("a promoted skill")
    return SandboxLauncher(SandboxConfig(image=IMAGE, skills_dir=skills))


def stage_dirs(tmp_path: Path) -> tuple[Path, Path, Path]:
    stage = tmp_path / "researching"
    out = stage / "out"
    out.mkdir(parents=True)
    out.chmod(0o777)
    spec = stage / "spec.json"
    spec.write_text("{}")
    spec.chmod(0o644)
    return stage, spec, out


def test_every_forbidden_access_fails(
    launcher: SandboxLauncher, relay_stub: int, tmp_path: Path
) -> None:
    stage, spec, out = stage_dirs(tmp_path)
    (out / "probe.py").write_text(PROBE % (str(ROOT), HOST_HOME, relay_stub))
    outcome = launcher.launch(
        stage_dir=stage,
        spec_path=spec,
        result_path=out / "result.json",
        relay_port=relay_stub,
        mcp_port=relay_stub,
        timeout=120,
        extra_env={},
        command=[WORKER_PYTHON, f"{CONTAINER_OUT}/probe.py"],
    )
    assert outcome.exit_code == 0, outcome
    results = json.loads((out / "probe.json").read_text())
    print(json.dumps(results, indent=1))  # the journal quotes these lines
    allowed = {name for name, verdict in results.items() if str(verdict).startswith("ALLOWED")}
    assert allowed == {"relay_via_forwarder"}, allowed
    assert results["relay_via_forwarder"] == "ALLOWED: b'relay-ok'"
    assert results["uid"] == 10001
    with pytest.raises(OSError):
        read_worker_json(out / "result.json")  # the planted symlink is never followed
    assert not (tmp_path / "skills" / "new-skill.md").exists()


def test_cancel_stops_the_worker_within_ten_seconds(
    launcher: SandboxLauncher, relay_stub: int, tmp_path: Path
) -> None:
    stage, spec, out = stage_dirs(tmp_path)
    timer = threading.Timer(3.0, launcher.cancel)
    timer.start()
    started = time.monotonic()
    outcome = launcher.launch(
        stage_dir=stage,
        spec_path=spec,
        result_path=out / "result.json",
        relay_port=relay_stub,
        mcp_port=relay_stub,
        timeout=120,
        extra_env={},
        command=[WORKER_PYTHON, "-c", "import time; time.sleep(120)"],
    )
    elapsed = time.monotonic() - started
    print(f"cancel: stop_seconds={launcher.last_stop_seconds} total={elapsed:.2f}")
    assert outcome.cancelled
    assert launcher.last_stop_seconds is not None and launcher.last_stop_seconds < 10
    assert elapsed < 3 + 10 + 5
    running = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}}"], capture_output=True, text=True, check=False
    ).stdout.split()
    leftovers = [n for n in running if n.startswith(("episalpha-worker-", "episalpha-fwd-"))]
    assert leftovers == [], leftovers


def test_timeout_stops_the_worker(
    launcher: SandboxLauncher, relay_stub: int, tmp_path: Path
) -> None:
    stage, spec, out = stage_dirs(tmp_path)
    outcome = launcher.launch(
        stage_dir=stage,
        spec_path=spec,
        result_path=out / "result.json",
        relay_port=relay_stub,
        mcp_port=relay_stub,
        timeout=3,
        extra_env={},
        command=[WORKER_PYTHON, "-c", "import time; time.sleep(120)"],
    )
    print(f"timeout: stop_seconds={outcome.stop_seconds} total={outcome.seconds}")
    assert outcome.timed_out
    assert outcome.stop_seconds is not None and outcome.stop_seconds < 10
