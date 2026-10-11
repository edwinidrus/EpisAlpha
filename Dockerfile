# EpisAlpha application image: the CLI, the browser workbench and the quality gate.
#
# A toolbox rather than a frozen build. compose.yaml bind-mounts the repository at its host path
# (the research worker's bind mounts are resolved by the host's Docker daemon) and keeps the
# Python environment in a named volume, synced from uv.lock at every start
# (container/app-entrypoint.sh). The build context is only that entrypoint (.dockerignore), so
# .env, the data and the repository never enter the image.
FROM python@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258

# git: cloning Hermes at its pinned commit and `git archive` for the worker image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# The Docker CLI only (no daemon), from docker:29.1.3-cli. It is used only by live runs and the
# worker build, and only when compose.live.yaml mounts the host's socket.
COPY --from=docker@sha256:4fa0ee1f3a7e4354c4ea34558b6d4ee32859baf4973d4c8ccc8e7fe3dd730c04 \
    /usr/local/bin/docker /usr/local/bin/docker

RUN pip install --no-cache-dir uv==0.11.6

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_CACHE_DIR=/opt/uv-cache \
    UV_PYTHON=/usr/local/bin/python3.12 \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    UV_FROZEN=1 \
    PATH=/opt/venv/bin:$PATH

# Writable by whichever host uid runs the container (EPISALPHA_UID); named volumes inherit it.
RUN mkdir -p /opt/venv /opt/uv-cache && chmod 1777 /opt/venv /opt/uv-cache

COPY container/app-entrypoint.sh /usr/local/bin/episalpha-entrypoint
ENTRYPOINT ["episalpha-entrypoint"]
CMD ["episalpha", "--help"]
