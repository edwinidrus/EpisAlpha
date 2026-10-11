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
# Dependencies first (cached layer), then an editable install so fixture paths resolve under /app.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --no-dev --no-install-project
COPY src ./src
RUN uv sync --no-dev
COPY apps ./apps
COPY harnesses ./harnesses
COPY eval_cases ./eval_cases
COPY scripts ./scripts
COPY worker ./worker
COPY container ./container
COPY config ./config
COPY .streamlit ./.streamlit
# Fake-runtime fixtures are shipped as runtime data; the rest of tests/ stays out of the image.
COPY tests/fixtures/runtime ./tests/fixtures/runtime
# Mount points, writable by whichever uid compose runs as (EPISALPHA_UID). A named volume
# mounted at /stages inherits this mode the first time it is created.
RUN mkdir -p /app/.episalpha /stages && chmod 1777 /app/.episalpha /stages
ENV EPISALPHA_CONFIG=config/demo.toml
CMD ["episalpha", "--help"]

FROM runtime AS dev
# The quality gate: pytest, ruff and mypy. compose.dev.yaml mounts the working copy over /app and
# keeps the editable install; UV_NO_SYNC keeps `uv run` on this venv.
RUN uv sync --all-groups
ENV UV_NO_SYNC=1
