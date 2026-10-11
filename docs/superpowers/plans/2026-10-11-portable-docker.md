# Portable Docker Orchestration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the whole EpisAlpha stack, including live Hermes runs, from `git clone` +
`docker compose build` with identical commands on Linux, macOS and Windows.

**Architecture:**
- **Images.** A multi-stage image bakes the code in: a `runtime` target and a `dev` target that
  adds the test tools.
- **Network.** A tiny `net` anchor container owns the published loopback ports. The UI, the CLI
  and Phoenix share its network namespace.
- **Live runs.** A new `compose` sandbox topology reaches the relay by Docker DNS and passes
  stage files through a named volume with sub-path mounts. Today's `host` topology stays the
  default outside Compose.

**Tech Stack:** Docker Engine ≥ 26 (API ≥ 1.45), Docker Compose ≥ 2.24 (`!reset`), uv 0.11.6,
Python 3.12, pytest. No new Python dependencies.

**Spec:** `docs/superpowers/specs/2026-10-11-portable-docker-design.md` (approved 2026-10-11)

## Global Constraints

- The minimum Docker Engine is 26, Docker Engine API 1.45, because of `volume-subpath`.
- Docker Compose must be 2.24 or newer (`!reset`). This host has v5.0.1.
- No registry, no image publishing, no CI. Images are built locally and natively per machine.
- No new Python dependencies (CLAUDE.md dependency policy).
- Base images stay pinned by digest:
  - Python: `python@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258`
  - Docker CLI: `docker@sha256:4fa0ee1f3a7e4354c4ea34558b6d4ee32859baf4973d4c8ccc8e7fe3dd730c04`
  - Phoenix: `arizephoenix/phoenix@sha256:2ac6874a4f743a626060adb6988b6dbd558530a0e06685334f63f8a779aaabb5`
- The only published ports are `127.0.0.1:8501` (UI) and `127.0.0.1:6006` (Phoenix).
- `otlp_endpoint` stays loopback-only in `settings.py`. It is not relaxed.
- Fixed `compose`-topology names, mirrored in Python constants:
  - network `episalpha-app`;
  - anchor service `net`;
  - stage volume `episalpha-stages`, mounted at `/stages`.
- The topology selector is the env var `EPISALPHA_SANDBOX_TOPOLOGY`, values `host` (default) or
  `compose`.
- Worker isolation is unchanged in both topologies (spec §4.3):
  - an internal, no-address network;
  - the forwarder as the only neighbour;
  - `--dns 127.0.0.1`;
  - read-only rootfs, `cap-drop ALL`, `no-new-privileges`, uid 10001, limits;
  - an image pinned by digest;
  - never mounting the data root, the database, `.env` or the socket.
- `.env` and `.episalpha/` never enter an image.
- Live model calls need fresh owner approval each time (CLAUDE.md). Commits and pushes are owner
  actions: run the commit steps only with the owner's go-ahead.
- Every step that runs `uv run …` on the host can also run in the dev container once Task 2
  lands.

## Review Focus

1. **Hermes chosen without the Docker socket.** The stack is running in `compose` mode without
   `compose.live.yaml` and someone picks the Hermes runtime. The run must be refused *before*
   admission with a message naming `compose.live.yaml`, never queued holding the job slot.
   Test: Task 5.
2. **A Linux user whose uid is not 1000.** Bind-mounted `.episalpha` files must stay owned by
   that user: every app service must render `user: "$EPISALPHA_UID:$EPISALPHA_GID"`.
   Test: Task 2.
3. **A Windows clone with `core.autocrlf=true`.** Dockerfiles and container scripts must keep LF
   endings. Test: Task 1 (`.gitattributes`).
4. **Secrets or data near the build context.** `.env`, `.episalpha/`, `.git/` or `.venv/` must
   never be sent into an image build. Test: Task 1 (`.dockerignore` allowlist).
5. **A fresh clone without `config/demo.toml`.** `docker compose run --rm cli …` must exit 2
   with "settings file … not found" and no traceback. Test: Task 2.

---

## File structure

| File | Responsibility | Task |
|---|---|---|
| `Dockerfile` (rewrite) | Multi-stage app image: `base`, `runtime` (code baked in), `dev` (+ test tools) | 1 |
| `.dockerignore` (rewrite) | Allowlist build context; secrets and data can never enter | 1 |
| `.gitattributes` (new) | LF line endings for container-relevant files | 1 |
| `container/app-entrypoint.sh` (delete) | Replaced: dependencies are installed at build time | 1 |
| `tests/integration/test_container_files.py` (new) | Static checks of `.dockerignore`, `.gitattributes`, `Dockerfile` | 1 |
| `compose.yaml` (rewrite) | Portable stack: `net`, `ui`, `cli`, `setup-worker`, `phoenix` | 2 |
| `compose.dev.yaml` (new) | Dev override: working copy at `/app`, `check` service | 2 |
| `compose.live.yaml` (edit) | Socket for `ui`/`cli`/`setup-worker`; Desktop `DOCKER_GID=0` note | 2 |
| `tests/integration/test_compose_config.py` (new) | `docker compose config --format json` assertions | 2 |
| `tests/integration/test_cli_research.py` (edit) | Missing settings file -> exit 2 | 2 |
| `HANDOFF.md`, `README.md` (edit) | OS-neutral Docker instructions | 3 |
| `docs/implementation/progress.md` (edit) | Amendment A15 | 3 |
| `implementation/M0-foundation/tasks/M0-T08-portable-docker.md` + journal, `PROGRESS.md`, `STATUS.md` | T1 task records | 3 |
| `src/episalpha/runtime/sandbox.py` (edit) | `compose` topology, `sandbox_config()`, `preflight()` | 4 |
| `tests/runtime/test_sandbox.py` (edit) | Command builders and preflight, both topologies | 4 |
| `src/episalpha/research/services.py` (edit) | Readiness preflight; work dir from topology | 5 |
| `tests/runtime/test_sandbox_services.py` (new) | Readiness refusals before admission | 5 |
| `tests/integration/test_runtime_boundary.py` (edit) | Probe runs in either topology | 5 |
| `implementation/M3-runtime/CONSTITUTION.md`, `implementation/M5-browser-obsidian/CONSTITUTION.md` (edit) | A15 wording | 6 |
| `implementation/M3-runtime/tasks/M3-T05-compose-topology.md` + journal, `GATE.md`, `PROGRESS.md`, `STATUS.md` | T2 task records, G3 re-run | 6 |

---

### Task 1: Portable app image

**Files:**
- Rewrite: `Dockerfile`
- Rewrite: `.dockerignore`
- Create: `.gitattributes`
- Delete: `container/app-entrypoint.sh`
- Test: `tests/integration/test_container_files.py`

**Interfaces:**
- Produces: image tags `episalpha-app:local` (target `runtime`) and `episalpha-app:dev`
  (target `dev`). In the image:
  - code lives at `/app` and the venv at `/opt/venv`;
  - `/app/.episalpha` and `/stages` exist with mode 1777;
  - `EPISALPHA_CONFIG=config/demo.toml`;
  - there is no `ENTRYPOINT`.
- `episalpha` (console script), `streamlit`, `python` and `docker` are on `PATH`.

- [ ] **Step 1: Write the failing static tests**

Create `tests/integration/test_container_files.py`:

```python
"""Portable Docker (M0-T08, A15): what may enter an image, and line endings for Windows clones.

Static checks only: no Docker needed. The image build itself is verified in the task journal.
"""

from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def context_includes(relative: str) -> bool:
    """Apply .dockerignore the way Docker does: the last matching pattern wins."""
    included = True
    for raw in (REPO / ".dockerignore").read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        negated = line.startswith("!")
        pattern = line.lstrip("!").rstrip("/")
        if fnmatch(relative, pattern) or fnmatch(relative, pattern + "/*"):
            included = negated
    return included


def test_secrets_data_and_history_never_enter_the_build_context() -> None:
    for path in (
        ".env",
        ".env.local",
        ".episalpha/app.sqlite3",
        ".git/config",
        ".venv/bin/python",
        "config/demo.toml",
        "tests/conftest.py",
        "src/episalpha/__pycache__/cli.cpython-312.pyc",
    ):
        assert not context_includes(path), path


def test_the_code_the_image_needs_is_in_the_build_context() -> None:
    for path in (
        "pyproject.toml",
        "uv.lock",
        "README.md",
        "src/episalpha/cli.py",
        "apps/streamlit_app.py",
        "harnesses/baseline/researcher.md",
        "eval_cases/demo/synthetic_corpus.json",
        "scripts/setup_worker.py",
        "worker/hermes_stage.py",
        "container/forwarder.py",
        "config/runtime.lock.json",
        "config/demo.example.toml",
        ".streamlit/config.toml",
    ):
        assert context_includes(path), path


def test_container_files_keep_lf_line_endings() -> None:
    rules = (REPO / ".gitattributes").read_text().splitlines()
    for pattern in ("Dockerfile", "*.sh", "*.py", "*.toml", "*.yaml"):
        assert f"{pattern} text eol=lf" in rules, pattern


def test_dockerfile_pins_bases_and_has_runtime_and_dev_targets() -> None:
    text = (REPO / "Dockerfile").read_text()
    assert "AS runtime" in text and "AS dev" in text
    for line in text.splitlines():
        if line.startswith("FROM ") and " AS " in line and "@sha256:" not in line:
            assert line.split()[1] in ("base", "runtime"), line  # stages, not registries
    assert "ENTRYPOINT" not in text
    assert "app-entrypoint" not in text
```

- [ ] **Step 2: Run the tests and watch them fail**

Run: `uv run pytest -q tests/integration/test_container_files.py`
Expected: FAIL. `.gitattributes` does not exist; `.dockerignore` excludes everything except the
entrypoint; the Dockerfile has no `AS runtime`.

- [ ] **Step 3: Write `.dockerignore`**

```gitignore
# Allowlist (A15): the app image gets exactly the code it runs. .env, .episalpha/, .git/, .venv/
# and the tests never enter the build context.
*
!pyproject.toml
!uv.lock
!README.md
!src/
!apps/
!harnesses/
!eval_cases/
!scripts/
!worker/
!container/
!config/
config/demo.toml
!.streamlit/
**/__pycache__
**/*.pyc
```

- [ ] **Step 4: Write `.gitattributes`**

```gitattributes
# A Windows clone with core.autocrlf=true must still build and run the Linux containers (A15).
Dockerfile text eol=lf
*.sh text eol=lf
*.py text eol=lf
*.toml text eol=lf
*.yaml text eol=lf
*.json text eol=lf
*.md text eol=lf
```

- [ ] **Step 5: Rewrite `Dockerfile`**

```dockerfile
# EpisAlpha application image (A15): the CLI, the browser workbench and the setup tools.
#
#   docker compose build            # target runtime -> episalpha-app:local
#   compose.dev.yaml                # target dev     -> episalpha-app:dev (+ pytest, ruff, mypy)
#
# The code is baked in at /app and the dependencies come from uv.lock at build time, so the image
# runs on any Docker host (amd64 or arm64; every base below is a multi-arch index). The build
# context is an allowlist (.dockerignore): .env, .episalpha/ and .git/ never enter it.
FROM python@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258 AS base

# git: cloning Hermes at its pinned commit and `git archive` for the worker image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# The Docker CLI only (no daemon), from docker:29.1.3-cli. Used by live runs and the worker build,
# and only when compose.live.yaml mounts the host's socket.
COPY --from=docker@sha256:4fa0ee1f3a7e4354c4ea34558b6d4ee32859baf4973d4c8ccc8e7fe3dd730c04 \
    /usr/local/bin/docker /usr/local/bin/docker

RUN pip install --no-cache-dir uv==0.11.6

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON=/usr/local/bin/python3.12 \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    UV_FROZEN=1 \
    UV_NO_CACHE=1 \
    PATH=/opt/venv/bin:$PATH
WORKDIR /app

FROM base AS runtime
# Dependencies first (cached layer), then the project itself, installed non-editable.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --no-dev --no-install-project
COPY src ./src
RUN uv sync --no-dev --no-editable
COPY apps ./apps
COPY harnesses ./harnesses
COPY eval_cases ./eval_cases
COPY scripts ./scripts
COPY worker ./worker
COPY container ./container
COPY config ./config
COPY .streamlit ./.streamlit
# Mount points, writable by whichever uid compose runs as (EPISALPHA_UID). A named volume
# mounted at /stages inherits this mode the first time it is created.
RUN mkdir -p /app/.episalpha /stages && chmod 1777 /app/.episalpha /stages
ENV EPISALPHA_CONFIG=config/demo.toml
CMD ["episalpha", "--help"]

FROM runtime AS dev
# The quality gate: pytest, ruff and mypy. compose.dev.yaml mounts the working copy over /app and
# puts /app/src first on PYTHONPATH; UV_NO_SYNC keeps `uv run` on this venv.
RUN uv sync --all-groups --no-editable
ENV UV_NO_SYNC=1
```

- [ ] **Step 6: Delete the old entrypoint**

Run: `git rm container/app-entrypoint.sh`

- [ ] **Step 7: Run the static tests**

Run: `uv run pytest -q tests/integration/test_container_files.py`
Expected: `4 passed`.

- [ ] **Step 8: Build both targets and smoke them**

Run:
```bash
docker build --target runtime -t episalpha-app:local .
docker build --target dev -t episalpha-app:dev .
docker run --rm episalpha-app:local episalpha --version
docker run --rm episalpha-app:local sh -c 'test ! -e /app/.env && test ! -e /app/.git && test ! -d /app/tests && echo clean'
docker run --rm episalpha-app:dev sh -c 'pytest --version && ruff --version && mypy --version'
```
Expected: `0.1.0`, `clean`, and three tool versions. Record the output in the journal.

- [ ] **Step 9: Run the four checks**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy src/episalpha && uv run pytest -q -m "not live"`
Expected: all green, `610 passed` (606 + 4).

- [ ] **Step 10: Commit (owner go-ahead only)**

```bash
git add Dockerfile .dockerignore .gitattributes tests/integration/test_container_files.py
git commit -m "A15: portable multi-stage app image; allowlist build context; LF endings"
```

---

### Task 2: Portable compose stack

**Files:**
- Rewrite: `compose.yaml`
- Create: `compose.dev.yaml`
- Modify: `compose.live.yaml` (header comment and `DOCKER_GID` default only)
- Test: `tests/integration/test_compose_config.py`
- Modify: `tests/integration/test_cli_research.py` (one test)

**Interfaces:**
- Consumes: images `episalpha-app:local` and `episalpha-app:dev` from Task 1.
- Produces, used by Tasks 4–6:
  - Docker network `episalpha-app` and volume `episalpha-stages`;
  - service `net`, which owns `127.0.0.1:8501` and `127.0.0.1:6006`;
  - `ui`, `cli` and `setup-worker` with `EPISALPHA_SANDBOX_TOPOLOGY=compose` and `/stages`
    mounted;
  - the `check` service in `compose.dev.yaml`.

- [ ] **Step 1: Write the failing compose tests**

Create `tests/integration/test_compose_config.py`:

```python
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
    if done.returncode != 0 and "is not a docker command" in done.stderr:
        pytest.skip("docker compose plugin not installed")
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
```

Append to `tests/integration/test_cli_research.py` (review focus 5):

```python
def test_a_missing_settings_file_is_a_clean_refusal(tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["--config", str(tmp_path / "absent.toml"), "demo", "seed"])
    assert result.exit_code == 2
    assert "settings file" in result.output and "not found" in result.output
    assert "Traceback" not in result.output
```

(`CliRunner` and `app` are already imported in that file.)

- [ ] **Step 2: Run the tests and watch them fail**

Run: `uv run pytest -q tests/integration/test_compose_config.py tests/integration/test_cli_research.py -k "compose or missing_settings"`
Expected:
- the compose tests FAIL: today's `compose.yaml` uses `network_mode: host`, there is no `net`
  service and no `compose.dev.yaml`;
- the CLI test PASSES already. It pins existing behaviour; record that in the journal.

- [ ] **Step 3: Rewrite `compose.yaml`**

```yaml
# EpisAlpha with Docker, the same commands on Linux, macOS and Windows (amendment A15).
# Run from the repository root. Needs Docker Engine >= 26 and Compose >= 2.24. Guide: HANDOFF.md.
#
#   docker compose build                                       # the app image
#   docker compose up -d                                       # UI 127.0.0.1:8501, Phoenix :6006
#   docker compose run --rm cli demo seed                      # the CLI
#   docker compose run --rm cli research run --case supported  # a fake (fixture) run
#   docker compose -f compose.yaml -f compose.dev.yaml run --rm check   # four checks + diagnose
#
# Live Hermes runs and the worker build add compose.live.yaml (the Docker socket).
name: episalpha

x-app: &app
  image: episalpha-app:local
  build: { context: ., target: runtime }
  # Your uid/gid on Linux, so files written into ./.episalpha stay yours.
  user: "${EPISALPHA_UID:-1000}:${EPISALPHA_GID:-1000}"
  # One shared namespace with the anchor and Phoenix: Phoenix is 127.0.0.1:6006 for the app,
  # exactly as on a host, so the loopback-only otlp_endpoint rule holds unchanged.
  network_mode: service:net
  depends_on: [net]
  working_dir: /app
  volumes:
    - ./.episalpha:/app/.episalpha
    - ./config:/app/config:ro
    - stages:/stages            # live-run stage files; the worker mounts only its own sub-path
  env_file:
    - path: .env                # git-ignored; the ENV: credentials named in config/demo.toml
      required: false
  environment:
    EPISALPHA_CONFIG: config/demo.toml
    EPISALPHA_SANDBOX_TOPOLOGY: compose
    HOME: /tmp

services:
  # The network anchor: owns the namespace and the only published ports (loopback only).
  net:
    image: episalpha-app:local
    build: { context: ., target: runtime }
    init: true
    command: ["python", "-c", "import signal; signal.pause()"]
    user: "${EPISALPHA_UID:-1000}:${EPISALPHA_GID:-1000}"
    networks: [app]
    ports:
      - "127.0.0.1:8501:8501"   # workbench
      - "127.0.0.1:6006:6006"   # Phoenix UI + OTLP/HTTP
    read_only: true
    cap_drop: [ALL]
    security_opt: ["no-new-privileges:true"]
    restart: unless-stopped

  ui:
    <<: *app
    # Inside the namespace Streamlit must listen on all interfaces: Docker delivers the published
    # port to the anchor's address, not to its 127.0.0.1. The host side is 127.0.0.1 only.
    command: ["streamlit", "run", "apps/streamlit_app.py", "--server.address", "0.0.0.0"]
    restart: unless-stopped

  cli:
    <<: *app
    profiles: [tools]
    entrypoint: ["episalpha"]
    command: ["--help"]

  setup-worker:
    <<: *app
    profiles: [tools]
    command: ["python", "scripts/setup_worker.py"]
    volumes:
      - ./.episalpha:/app/.episalpha
      - ./config:/app/config      # writable: --record updates config/runtime.lock.json
      - stages:/stages

  phoenix:
    extends: { file: observability/compose.yaml, service: phoenix }
    network_mode: service:net
    depends_on: [net]
    ports: !reset []
    networks: !reset []

volumes:
  stages:
    name: episalpha-stages

networks:
  app:
    name: episalpha-app
```

`observability/compose.yaml` stays unchanged, so `docker compose -f observability/compose.yaml
up -d` still serves a non-container `uv run` setup.

- [ ] **Step 4: Create `compose.dev.yaml`**

```yaml
# Development override (A15): run the working copy instead of the baked-in code.
#
#   docker compose -f compose.yaml -f compose.dev.yaml build
#   docker compose -f compose.yaml -f compose.dev.yaml run --rm check   # four checks + diagnose
#   docker compose -f compose.yaml -f compose.dev.yaml up -d ui         # UI on your working copy
x-dev: &dev
  image: episalpha-app:dev
  build: { context: ., target: dev }
  environment:
    PYTHONPATH: /app/src          # the working copy wins over the venv's installed package
    GIT_CONFIG_COUNT: "1"         # diagnose reads git; bind-mounted repos may look foreign
    GIT_CONFIG_KEY_0: safe.directory
    GIT_CONFIG_VALUE_0: /app

services:
  ui:
    <<: *dev
    volumes:
      - .:/app
  cli:
    <<: *dev
    volumes:
      - .:/app
  check:
    <<: *dev
    user: "${EPISALPHA_UID:-1000}:${EPISALPHA_GID:-1000}"
    profiles: [tools]
    working_dir: /app
    network_mode: none            # the default suite is offline by contract
    volumes:
      - .:/app
    environment:
      PYTHONPATH: /app/src
      HOME: /tmp
      GIT_CONFIG_COUNT: "1"
      GIT_CONFIG_KEY_0: safe.directory
      GIT_CONFIG_VALUE_0: /app
    command: ["python", "scripts/diagnose.py"]
```

- [ ] **Step 5: Edit `compose.live.yaml`**

Keep the `x-socket` block and its service list (`ui`, `cli`, `setup-worker`). Replace the header
comment with:

```yaml
# Live Hermes runs from the containers, on any OS (A15). Needs Docker Engine >= 26.
#
#   Linux:          DOCKER_GID=$(stat -c %g /var/run/docker.sock)   (or put it in a shell .env)
#   Docker Desktop: DOCKER_GID=0
#
#   docker compose -f compose.yaml -f compose.live.yaml run --rm setup-worker   # once per machine
#   docker compose -f compose.yaml -f compose.live.yaml up -d
#   docker compose -f compose.yaml -f compose.live.yaml run --rm cli \
#       research run --case supported --runtime hermes
#
# WARNING: the Docker socket gives these containers control of the host's Docker daemon, which is
# root-equivalent on a rootful engine. Only the trusted application gets it, never the research
# worker. That is why it lives in this separate file and not in compose.yaml.
```

- [ ] **Step 6: Run the compose tests**

Run: `uv run pytest -q tests/integration/test_compose_config.py`
Expected: `6 passed`.

- [ ] **Step 7: Bring the stack up on this host and smoke it**

Run, recording every output in the journal:
```bash
docker compose down --remove-orphans                        # stop the old host-network stack
docker compose build
docker compose up -d
curl -s 127.0.0.1:8501/_stcore/health                       # expect: ok
curl -s -o /dev/null -w '%{http_code}\n' 127.0.0.1:6006/    # expect: 200
ss -ltn | grep -E ':(8501|6006) '                           # expect: 127.0.0.1 only
docker compose run --rm cli demo seed
docker compose run --rm cli research run --case supported   # expect [FIXTURE], exit 0
docker compose run --rm cli export obsidian --run <run_id from the line above>
ls .episalpha/exports/vault/generated/                      # the vault is on the host
docker compose -f compose.yaml -f compose.dev.yaml build
docker compose -f compose.yaml -f compose.dev.yaml run --rm check   # expect diagnose PASS
```
Expected:
- health `ok` and Phoenix `200`, with only loopback listeners;
- a fake run at `RESEARCH_COMPLETED` and the run's directory in the vault;
- `check` reports `diagnose: PASS` with `611 passed, 6 skipped`. The compose tests skip inside
  the container, which has no compose plugin; on the host they run.

Then:
- open `http://127.0.0.1:6006` and confirm the `research.run` trace of that fake run is listed;
- remove the old toolbox volumes if present: `docker volume rm episalpha_venv episalpha_uv-cache`.

- [ ] **Step 8: Run the four checks on the host**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy src/episalpha && uv run pytest -q -m "not live"`
Expected: all green, `617 passed` (610 + 6 + 1).

- [ ] **Step 9: Commit (owner go-ahead only)**

```bash
git add compose.yaml compose.dev.yaml compose.live.yaml tests/integration/test_compose_config.py tests/integration/test_cli_research.py
git commit -m "A15: portable compose stack (network anchor, relative mounts, dev override)"
```

---

### Task 3: T1 docs and records (M0-T08)

**Files:**
- Modify: `HANDOFF.md` (§3 "Bring it up on a new machine" and §4 "Live Hermes runs")
- Modify: `README.md` (Docker block)
- Modify: `docs/implementation/progress.md` (append amendment A15)
- Create: `implementation/M0-foundation/tasks/M0-T08-portable-docker.md`
- Create: `implementation/M0-foundation/tasks/M0-T08-portable-docker.journal.md`
- Modify: `implementation/M0-foundation/PROGRESS.md`, `implementation/STATUS.md`

**Interfaces:**
- Consumes: the commands and outputs recorded in Tasks 1–2.
- Produces: STATUS rows `M0-T08` (DONE) and `M3-T05` (TODO, depends on M0-T08).

- [ ] **Step 1: Rewrite the HANDOFF Docker sections**

In HANDOFF §3:
- Replace the Linux-only prerequisites and the `${PWD}` / same-absolute-path explanation with
  the block below.
- Keep the data-transfer instructions (`tar czf episalpha-data.tgz …`).
- Delete the sentence saying Docker Desktop cannot run live runs.

```markdown
Prerequisites: Docker Engine >= 26 with Compose >= 2.24 (Docker Desktop on macOS or Windows, or
Docker Engine on Linux). Then, from the repository root:

    cp config/demo.example.toml config/demo.toml   # Windows PowerShell: Copy-Item
    # put the credentials into .env (names only are listed in config/demo.toml)
    docker compose build
    docker compose up -d                            # UI http://127.0.0.1:8501, Phoenix :6006
    docker compose run --rm cli demo seed
    docker compose run --rm cli research run --case supported     # a [FIXTURE] fake run
    docker compose run --rm cli replay <run_id>
    docker compose run --rm cli export obsidian --run <run_id>     # vault: .episalpha/exports/vault
    docker compose -f compose.yaml -f compose.dev.yaml run --rm check   # expect diagnose: PASS

On Linux, if your uid/gid are not 1000, set EPISALPHA_UID and EPISALPHA_GID (for example in
your shell, or in a `.env` next to compose.yaml) so files in .episalpha stay yours.
```

In HANDOFF §4, use the `compose.live.yaml` header commands from Task 2 Step 5. Note that the
`compose` sandbox topology arrives with M3-T05: until then, live runs still need Linux host
mode.

- [ ] **Step 2: Update the README Docker block**

Replace it with the five commands `build`, `up -d`, `run --rm cli research run --case
supported`, `run --rm cli export obsidian --run <run_id>` and the dev `check` command from Step
1. Add one sentence: "Works the same on Linux, macOS and Windows (Docker Engine >= 26)."

- [ ] **Step 3: Record amendment A15**

Append to the amendments section of `docs/implementation/progress.md`:

```markdown
### A15 — Portable Docker orchestration (owner approved 2026-10-11)

- **Decision:** the full stack, live Hermes runs included, runs from `git clone` +
  `docker compose build` on Linux, macOS and Windows. Distribution by local build only.
  Approach A (Docker-native).
- **Design:** `docs/superpowers/specs/2026-10-11-portable-docker-design.md`.
  **Plan:** `docs/superpowers/plans/2026-10-11-portable-docker.md`.
- **Changes approved with it:**
  1. The app and Phoenix share one network namespace (anchor `net`). Phoenix leaves its own
     network but stays loopback-only from the host.
  2. In the `compose` sandbox topology, the relay and MCP server listen inside that namespace
     (reachable on `episalpha-app` only, token-protected) instead of on the `docker0` gateway.
  3. Docker Engine >= 26 (API 1.45) is required.
  4. M5 constitution article 9 now reads "reachable from the host's loopback only".
- **Tasks:**
  - M0-T08: portable offline stack;
  - M3-T05: `compose` sandbox topology and live check. This reopens G3.
- **Owner checks outstanding:** macOS Apple Silicon and Windows Docker Desktop. Run build →
  check → up → fake run → live run, and confirm the `DOCKER_GID=0` socket access and the arm64
  Hermes build.
```

- [ ] **Step 4: Create the M0-T08 task pack and journal**

`implementation/M0-foundation/tasks/M0-T08-portable-docker.md`:
- Copy the structure of `implementation/templates/TASK.md`.
- Status: DONE. Depends on: M5-T03.
- Plan source: A15 spec §3 and plan Tasks 1–3.
- Acceptance: the Task 1 Step 8 and Task 2 Step 7 checks.

`…journal.md`: one Attempt block in the README format, with the real outputs from Task 1 Step 8
and Task 2 Step 7.

- [ ] **Step 5: Update PROGRESS and STATUS**

- `implementation/M0-foundation/PROGRESS.md`: add the M0-T08 row (Task / Status / Changes /
  Verification with exact commands and results / Blocker "macOS+Windows owner check" / Next
  M3-T05).
- `implementation/STATUS.md`:
  - add rows `M0-T08` (DONE) and `M3-T05 | Compose sandbox topology (A15) | TODO | M0-T08`;
  - set **Next task** to `M3-T05`;
  - mark G3 as "reopened by A15 (M3-T05)".

- [ ] **Step 6: Diagnose**

Run: `uv run python scripts/diagnose.py`
Expected: `diagnose: PASS … regressions 0 | orphans 0`. Orphans must stay 0: the new task pack
and STATUS row must reference each other.

- [ ] **Step 7: Commit (owner go-ahead only)**

```bash
git add HANDOFF.md README.md docs/implementation/progress.md implementation/
git commit -m "M0-T08: portable Docker stack docs and records (A15)"
```

---

### Task 4: `compose` sandbox topology in `sandbox.py`

**Files:**
- Modify: `src/episalpha/runtime/sandbox.py`:
  - the docstring;
  - `SandboxConfig` (around line 68);
  - `forwarder_command` (around line 125);
  - `worker_command` (around line 146);
  - `SandboxLauncher.__init__` (around line 192);
  - new functions `sandbox_config` and `preflight`.
- Test: `tests/runtime/test_sandbox.py`

**Interfaces:**
- Produces, used by Task 5:
  - `Topology = Literal["host", "compose"]`;
  - `TOPOLOGY_ENV = "EPISALPHA_SANDBOX_TOPOLOGY"`;
  - `COMPOSE_APP_NETWORK = "episalpha-app"`, `COMPOSE_RELAY_HOST = "net"`,
    `COMPOSE_STAGE_VOLUME = "episalpha-stages"`, `COMPOSE_STAGE_ROOT = Path("/stages")`;
  - `MIN_DOCKER_API = (1, 45)`;
  - `SandboxConfig.topology: Topology = "host"`;
  - properties `SandboxConfig.forward_target -> str`, `.forwarder_network -> str`,
    `.bind_host -> str` and `.stage_root -> Path | None`;
  - `sandbox_config(image: str, environ: Mapping[str, str]) -> SandboxConfig`, which raises
    `ValueError` on an unknown topology;
  - `preflight(config: SandboxConfig, runner: Runner = _docker) -> str | None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/runtime/test_sandbox.py`. Extend its import from `episalpha.runtime.sandbox`
with `COMPOSE_STAGE_ROOT, preflight, sandbox_config`:

```python
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
```

Add `from typing import Any` to the file's imports.

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run pytest -q tests/runtime/test_sandbox.py`
Expected: an ImportError on `COMPOSE_STAGE_ROOT`, `preflight` and `sandbox_config`.

- [ ] **Step 3: Implement in `sandbox.py`**

Add after the existing `FORWARDER_SCRIPT` constant:

```python
Topology = Literal["host", "compose"]
TOPOLOGY_ENV = "EPISALPHA_SANDBOX_TOPOLOGY"
COMPOSE_APP_NETWORK = "episalpha-app"
COMPOSE_RELAY_HOST = "net"
COMPOSE_STAGE_VOLUME = "episalpha-stages"
COMPOSE_STAGE_ROOT = Path("/stages")
MIN_DOCKER_API = (1, 45)
"""``volume-subpath`` mounts need Docker Engine API 1.45 (Engine 26)."""
```

Add `Literal` to the `typing` import. In `SandboxConfig`, add `topology: Topology = "host"`
directly after `image`, and these members after `docker`:

```python
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
        namespace, reachable only from episalpha-app (the forwarder), never published."""
        return "0.0.0.0" if self.topology == "compose" else self.host_gateway

    @property
    def stage_root(self) -> Path | None:
        """The stage volume's mount point in compose; ``None`` means host bind mounts."""
        return COMPOSE_STAGE_ROOT if self.topology == "compose" else None
```

This replaces the existing `__post_init__`; keep its image check as shown. Then add:

```python
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
    return (
        f"type=volume,src={COMPOSE_STAGE_VOLUME},dst={target},volume-subpath={sub_path}{suffix}"
    )
```

In `worker_command`, replace the two stage mount strings with:

```python
    mounts = [
        "--mount",
        _mount(config, spec_path, CONTAINER_SPEC, readonly=True),
        "--mount",
        _mount(config, out_dir, CONTAINER_OUT, readonly=False),
    ]
```

In `forwarder_command`, replace `"bridge"` with `config.forwarder_network`, and both
`config.host_gateway` targets with `config.forward_target`. In `SandboxLauncher.__init__`,
replace `self.bind_host = config.host_gateway` with `self.bind_host = config.bind_host`. Add:

```python
def preflight(config: SandboxConfig, runner: Runner = _docker) -> str | None:
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
```

Rewrite the module docstring's Worker network, Forwarder and Mounts bullets so they name both
topologies (spec §4.2). Keep every hardening bullet as is.

- [ ] **Step 4: Run the sandbox tests**

Run: `uv run pytest -q tests/runtime/test_sandbox.py`
Expected: all pass. That includes the untouched host tests, `test_forwarder_targets_are_fixed`
and `test_urls_point_at_the_forwarder_only`, unmodified.

- [ ] **Step 5: Run the four checks**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy src/episalpha && uv run pytest -q -m "not live"`
Expected: all green, 626 passed (617 + 9).

- [ ] **Step 6: Commit (owner go-ahead only)**

```bash
git add src/episalpha/runtime/sandbox.py tests/runtime/test_sandbox.py
git commit -m "M3-T05: compose sandbox topology (forwarder by name, stage volume sub-paths, preflight)"
```

---

### Task 5: Wire the topology into services and the live boundary probe

**Files:**
- Modify: `src/episalpha/research/services.py`: `_hermes_readiness` (around line 588) and
  `_hermes_runtime` (around line 604)
- Create: `tests/runtime/test_sandbox_services.py`
- Modify: `tests/integration/test_runtime_boundary.py`: a module-level `CONFIG`, one line
  of the `relay_stub` fixture, the `launcher` fixture, `stage_dirs` and one assertion

**Interfaces:**
- Consumes: `sandbox_config`, `preflight` and `SandboxConfig.stage_root` / `.bind_host` from
  Task 4.
- Produces: in `compose` mode, a Hermes submission is refused before admission with
  `EpisAlphaError(INVALID_REQUEST, "no isolated worker available: <preflight reason>")`. The
  stage work dir is `/stages` in compose and `<data_root>/work` otherwise.

- [ ] **Step 1: Write the failing services tests**

Create `tests/runtime/test_sandbox_services.py`:

```python
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
```

`preflight`'s default `runner=_docker` is bound when the function is defined, so patching
`sandbox._docker` would not reach it. `_hermes_readiness` must therefore call
`preflight(config, sandbox._docker)`, looking the runner up at call time. Step 3 does exactly
that, and the first test proves it.

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run pytest -q tests/runtime/test_sandbox_services.py`
Expected: the first two FAIL. Today's readiness returns the lock without checking the topology,
so no error is raised.

- [ ] **Step 3: Implement in `services.py`**

In `_hermes_readiness`, after the existing `if not image or not shutil.which("docker"):` refusal,
add:

```python
    from episalpha.runtime import sandbox

    try:
        config = sandbox.sandbox_config(str(image), os.environ)
    except ValueError as error:
        raise _refuse(f"no isolated worker available: {error}") from None
    problem = sandbox.preflight(config, sandbox._docker)
    if problem is not None:
        raise _refuse(f"no isolated worker available: {problem}")
```

In `_hermes_runtime`:
- change the local import to `from episalpha.runtime.sandbox import SandboxLauncher,
  sandbox_config`;
- replace `launcher = SandboxLauncher(SandboxConfig(image=image))` with:

```python
        sandbox_settings = sandbox_config(image, os.environ)
        launcher = SandboxLauncher(sandbox_settings)
        stage_root = sandbox_settings.stage_root
```

- initialise `stage_root: Path | None = None` before the `if os.environ.get("EPISALPHA_WORKER")
  == "local":` branch;
- replace `work_dir=workbench.data_root / "work",` with
  `work_dir=stage_root or workbench.data_root / "work",`.

- [ ] **Step 4: Run the services tests and the four checks**

Run: `uv run pytest -q tests/runtime/test_sandbox_services.py && uv run ruff check . && uv run ruff format --check . && uv run mypy src/episalpha && uv run pytest -q -m "not live"`
Expected: all green, 629 passed (626 + 3).

- [ ] **Step 5: Make the live boundary probe topology-aware**

In `tests/integration/test_runtime_boundary.py`:
- add `import os` and `import uuid`;
- import `sandbox_config` alongside `SandboxConfig`;
- add the module-level `CONFIG` and replace the `launcher` fixture and `stage_dirs` with:

```python
CONFIG = sandbox_config(IMAGE or "sha256:" + "0" * 64, os.environ)


@pytest.fixture
def launcher(tmp_path: Path) -> SandboxLauncher:
    if not IMAGE or shutil.which("docker") is None:
        pytest.skip("Docker or the pinned worker image is not available")
    if CONFIG.topology == "compose":
        return SandboxLauncher(CONFIG)  # no skills mount in compose yet (M8)
    skills = tmp_path / "skills"
    skills.mkdir()
    (skills / "promoted.md").write_text("a promoted skill")
    return SandboxLauncher(SandboxConfig(image=IMAGE, skills_dir=skills))


def stage_dirs(tmp_path: Path) -> tuple[Path, Path, Path]:
    root = CONFIG.stage_root / f"probe-{uuid.uuid4().hex[:8]}" if CONFIG.stage_root else tmp_path
    stage = root / "researching"
    out = stage / "out"
    out.mkdir(parents=True)
    out.chmod(0o777)
    spec = stage / "spec.json"
    spec.write_text("{}")
    spec.chmod(0o644)
    return stage, spec, out
```

Leave the module-scoped `relay_stub` fixture as it is, except for one line: change
`server = HTTPServer(("172.17.0.1", 0), Handler)` to
`server = HTTPServer((CONFIG.bind_host, 0), Handler)`. Then, in
`test_every_forbidden_access_fails`, change the last assertion to:

```python
    if CONFIG.topology == "host":
        assert not (tmp_path / "skills" / "new-skill.md").exists()
```

- [ ] **Step 6: Run the probe in both topologies (no model calls)**

Host topology, on this host:
`uv run pytest -q -m live tests/integration/test_runtime_boundary.py`
Expected: `3 passed`, with `allowed == {"relay_via_forwarder"}` printed. Record the printed
verdicts.

Compose topology, inside the stack:
```bash
export DOCKER_GID=$(stat -c %g /var/run/docker.sock)
docker compose -f compose.yaml -f compose.dev.yaml -f compose.live.yaml up -d
docker compose -f compose.yaml -f compose.dev.yaml -f compose.live.yaml run --rm \
    --entrypoint pytest cli -q -m live tests/integration/test_runtime_boundary.py
```
Expected: `3 passed`. Every probe is BLOCKED except `relay_via_forwarder`, and the worker uid is
10001. Record the verdicts in the M3-T05 journal.

- [ ] **Step 7: Commit (owner go-ahead only)**

```bash
git add src/episalpha/research/services.py tests/runtime/test_sandbox_services.py tests/integration/test_runtime_boundary.py
git commit -m "M3-T05: wire the compose topology into readiness and the runtime; probe both topologies"
```

---

### Task 6: Live check, G3 re-run and T2 records (M3-T05)

**Files:**
- Modify: `implementation/M3-runtime/CONSTITUTION.md` (the article naming `docker0`)
- Modify: `implementation/M5-browser-obsidian/CONSTITUTION.md` (article 9)
- Modify: `HANDOFF.md` §4: drop the "until M3-T05" note from Task 3
- Create: `implementation/M3-runtime/tasks/M3-T05-compose-topology.md`
- Create: `implementation/M3-runtime/tasks/M3-T05-compose-topology.journal.md`
- Modify: `implementation/M3-runtime/GATE.md`, `implementation/M3-runtime/PROGRESS.md`,
  `implementation/STATUS.md`

**Interfaces:**
- Consumes: everything above.
- Produces: G3 re-run result; STATUS `M3-T05` DONE (or BLOCKED with reason); next task back to
  `M5-T04`.

- [ ] **Step 1: Update the constitution wording**

- **M3 constitution:** where an article says the relay and tool server bind the `docker0`
  gateway, reword it to: "bind the `docker0` gateway in the `host` topology, or the shared app
  namespace in the `compose` topology (A15); in both, only the forwarder can reach them."
  `grep -n docker0 implementation/M3-runtime/CONSTITUTION.md` finds the line.
- **M5 article 9:** replace "Streamlit binds to `127.0.0.1` in v0.1" with "Streamlit is
  reachable from the host's loopback only in v0.1 (A15: inside the compose namespace it listens
  on all interfaces; the published port is `127.0.0.1` only)."

- [ ] **Step 2: Ask the owner before the live run (STOP)**

Ask exactly:

> "Ready for the one live Hermes run in the compose topology: `docker compose -f compose.yaml
> -f compose.live.yaml run --rm cli research run --case supported --runtime hermes`. It spends
> about 8 OpenRouter requests (free tier: 50/day). Approve?"

Proceed only on an explicit yes. On no, record M3-T05 as DONE_OFFLINE with the reason, and skip
to Step 4.

- [ ] **Step 3: Run the live check**

```bash
export DOCKER_GID=$(stat -c %g /var/run/docker.sock)
docker compose -f compose.yaml -f compose.live.yaml run --rm setup-worker   # only if the image ID changed
docker compose -f compose.yaml -f compose.live.yaml up -d
docker compose -f compose.yaml -f compose.live.yaml run --rm cli research run --case supported --runtime hermes
docker compose -f compose.yaml -f compose.live.yaml run --rm cli replay <run_id>
```
Expected:
- a terminal state with the real `served_by` provider and the real usage. An honest
  `ABSTAINED`, `PARTIAL` or `REJECTED` is acceptable, since a live model may not complete the
  case. Record exactly what happened; never relabel a failure.
- the `research.run` trace visible in Phoenix at `127.0.0.1:6006`;
- `docker ps -a --filter name=episalpha-` shows no leftover worker or forwarder.

If the run fails for an infrastructure reason (worker did not start, relay unreachable), that is
a defect: debug it under superpowers:systematic-debugging, with two bounded attempts, then
BLOCKED.

- [ ] **Step 4: Re-run G3 and record**

Run the commands listed in `implementation/M3-runtime/GATE.md`, plus the compose-topology probe
from Task 5 Step 6. Append a dated "Re-run after A15 (M3-T05)" block with the real outputs.
Do not edit earlier blocks.

- [ ] **Step 5: Task records**

- Create the M3-T05 pack (template structure; acceptance = Task 4–6 checks) and journal (one
  Attempt block with the real outputs, including the live run or the DONE_OFFLINE reason).
- `implementation/M3-runtime/PROGRESS.md`: add the M3-T05 row.
- `implementation/STATUS.md`:
  - M3-T05 → DONE (or DONE_OFFLINE);
  - G3 → "PASSED <date> (re-run after A15)" or its real state;
  - **Next task** → `M5-T04`.
- `HANDOFF.md` §4: remove the "until M3-T05" note and give the expected check count.

- [ ] **Step 6: Four checks and diagnose**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy src/episalpha && uv run pytest -q -m "not live" && uv run python scripts/diagnose.py`
Expected: all green and `diagnose: PASS … regressions 0 | orphans 0`.

- [ ] **Step 7: Commit (owner go-ahead only)**

```bash
git add implementation/ HANDOFF.md
git commit -m "M3-T05: compose topology live check, G3 re-run, constitution wording (A15)"
```
