#!/bin/sh
# Sync the project environment from uv.lock (a no-op when nothing changed), then run the command.
set -eu
uv sync --frozen --all-groups --quiet
exec "$@"
