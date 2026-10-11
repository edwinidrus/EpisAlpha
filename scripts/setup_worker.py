"""Reproduce the pinned Hermes worker on a new machine (M3-T03/T04; HANDOFF.md section 4).

    uv run python scripts/setup_worker.py               # clone Hermes at the pin, build the image
    uv run python scripts/setup_worker.py --record      # ... and record the new image ID
    uv run python scripts/setup_worker.py --local-venv  # ... and the local-launcher venv (dev)

In Docker: ``docker compose -f compose.yaml -f compose.live.yaml run --rm setup-worker``.

The pin is ``config/runtime.lock.json`` (``hermes.upstream``, ``hermes.inspected_commit``). The
image is built by the same recipe as M3-T04 (:func:`episalpha.runtime.sandbox.build_image`).
Docker builds are not bit-for-bit reproducible: a rebuild from the same pinned base, lock and
commit gets a new content ID. The sandbox launcher runs the ID in the lock, so ``--record``
writes the new one there; review that diff before committing it.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from episalpha.runtime.sandbox import build_image

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "config" / "runtime.lock.json"
VENDOR = ROOT / ".episalpha" / "vendor"


def git(*args: str) -> str:
    done = subprocess.run(["git", *args], check=True, capture_output=True, text=True)
    return done.stdout.strip()


def checkout(upstream: str, commit: str, source: Path) -> None:
    """A clone of ``upstream`` at exactly ``commit`` (detached), or an error."""
    if not (source / ".git").is_dir():
        source.parent.mkdir(parents=True, exist_ok=True)
        git("clone", "--filter=blob:none", "--no-checkout", upstream, str(source))
    if git("-C", str(source), "rev-parse", "HEAD") != commit:
        git("-C", str(source), "fetch", "--filter=blob:none", "origin", commit)
        git("-C", str(source), "checkout", "--quiet", "--detach", commit)
    if git("-C", str(source), "rev-parse", "HEAD") != commit:
        raise SystemExit(f"Hermes checkout is not at the pinned commit {commit}")


def local_venv(source: Path, venv: Path) -> None:
    """The venv the local launcher uses (``EPISALPHA_WORKER=local``): Hermes' own lock + mcp."""
    environment = {**os.environ, "UV_PROJECT_ENVIRONMENT": str(venv)}
    subprocess.run(
        ["uv", "sync", "--frozen", "--no-dev", "--extra", "mcp"],
        cwd=source,
        env=environment,
        check=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--record", action="store_true", help="write the new image ID to the lock")
    parser.add_argument("--local-venv", action="store_true", help="also build the local venv")
    args = parser.parse_args()

    lock = json.loads(LOCK.read_text())
    hermes = lock["hermes"]
    upstream, commit = hermes["upstream"], hermes["inspected_commit"]
    image = hermes["worker_image"]
    source = VENDOR / "hermes-agent"

    checkout(upstream, commit, source)
    print(f"hermes: {source} at {commit}")
    if args.local_venv:
        local_venv(source, VENDOR / "hermes-venv")
        print(f"local venv: {VENDOR / 'hermes-venv'}")

    built = build_image(hermes_source=source, commit=commit, repo_root=ROOT, tag=image["tag"])
    print(f"worker image: {image['tag']} {built}")
    if built == image["id"]:
        print("matches the lock")
        return 0
    if not args.record:
        print(f"differs from the lock ({image['id']}); use --record to adopt it", file=sys.stderr)
        return 1
    image["id"] = built
    image["built_at"] = datetime.now(UTC).date().isoformat()
    LOCK.write_text(json.dumps(lock, indent=2, ensure_ascii=False) + "\n")
    print(f"recorded in {LOCK.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
