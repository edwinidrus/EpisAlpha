#!/usr/bin/env python3
"""Offline demo smoke for EpisAlpha (M7-T02): the whole demo in one command.

    uv run python scripts/demo_smoke.py                    # exit 0 when every step held
    uv run python scripts/demo_smoke.py --inject-failure   # self-test: must exit non-zero

Everything happens on temporary state: a fresh data root and settings file under the system
temporary directory. The real ``.episalpha/`` and ``config/demo.toml`` are never read, and no
credential is needed. Every run is a fake-runtime FIXTURE, never research.

Steps, each checked before the next: seed; the three demo cases; replay of each run with
every non-loopback connection refused; Obsidian export; ``experiment compare --runtime fake``
(the development label drafts copied into a sealed directory outside both roots); backup of
the database, object store and runs as one unit, restore into a new data root, every hash
verified, and a replay from the restored copy. Prints where everything is.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LABEL_DRAFTS = REPO_ROOT / "docs" / "implementation" / "m6-label-drafts" / "development"
CASES = ("supported", "conflicting", "insufficient")
FIXTURE = "[FIXTURE] fake runtime"
# Runs the CLI with every non-loopback connection and name lookup refused.
OFFLINE_CLI = """
import ipaddress, socket, sys
def _local(host):
    try:
        return host in (None, "localhost") or ipaddress.ip_address(str(host)).is_loopback
    except ValueError:
        return False
_connect, _lookup = socket.socket.connect, socket.getaddrinfo
def connect(self, address):
    if self.family in (socket.AF_INET, socket.AF_INET6) and not _local(address[0]):
        raise OSError(f"smoke: network blocked ({address[0]})")
    return _connect(self, address)
def lookup(host, *args, **kwargs):
    if not _local(host):
        raise OSError(f"smoke: network blocked ({host})")
    return _lookup(host, *args, **kwargs)
socket.socket.connect, socket.getaddrinfo = connect, lookup
from episalpha.cli import app
sys.argv = ["episalpha", *sys.argv[1:]]
app()
"""


class SmokeFailure(Exception):
    pass


def check(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


def write_settings(path: Path, data_root: Path, labels: Path) -> Path:
    path.write_text(
        f'[paths]\nproject_root = "{REPO_ROOT}"\ndata_root = "{data_root}"\n\n'
        f'[evaluation]\nlabels_dir = "{labels}"\n'
    )
    return path


def cli(settings: Path, *arguments: str, offline: bool = False) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("EPISALPHA_")}
    env["EPISALPHA_CONFIG"] = str(settings)
    command = (
        [sys.executable, "-c", OFFLINE_CLI, "--config", str(settings), *arguments]
        if offline
        else [sys.executable, "-m", "episalpha.cli", "--config", str(settings), *arguments]
    )
    return subprocess.run(
        command, capture_output=True, text=True, env=env, cwd=REPO_ROOT, timeout=300, check=False
    )


def tree_hashes(*roots: Path) -> dict[str, str]:
    found = {}
    for root in roots:
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            found[f"{root.name}/{path.relative_to(root).as_posix()}"] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    return found


def backup(data_root: Path, target: Path) -> dict[str, str]:
    """Database (consistent copy through SQLite's backup API), objects and runs, as one unit."""
    target.mkdir(parents=True)
    with (
        sqlite3.connect(data_root / "app.sqlite3") as source,
        sqlite3.connect(target / "app.sqlite3") as copy,
    ):
        source.backup(copy)
    for name in ("objects", "runs"):
        shutil.copytree(data_root / name, target / name)
    hashes = tree_hashes(target / "objects", target / "runs")
    hashes["app.sqlite3"] = hashlib.sha256((target / "app.sqlite3").read_bytes()).hexdigest()
    (target / "MANIFEST.json").write_text(json.dumps(hashes, indent=1, sort_keys=True))
    return hashes


def restore(backup_dir: Path, data_root: Path) -> None:
    """Restore all three parts together, refusing the unit if any hash differs."""
    expected = json.loads((backup_dir / "MANIFEST.json").read_text())
    actual = tree_hashes(backup_dir / "objects", backup_dir / "runs")
    actual["app.sqlite3"] = hashlib.sha256((backup_dir / "app.sqlite3").read_bytes()).hexdigest()
    check(actual == expected, "backup hashes do not match their manifest; nothing restored")
    data_root.mkdir(parents=True)
    shutil.copy2(backup_dir / "app.sqlite3", data_root / "app.sqlite3")
    for name in ("objects", "runs"):
        shutil.copytree(backup_dir / name, data_root / name)
    restored = tree_hashes(data_root / "objects", data_root / "runs")
    restored["app.sqlite3"] = hashlib.sha256((data_root / "app.sqlite3").read_bytes()).hexdigest()
    check(restored == expected, "restored files differ from the backup")


def run(inject_failure: bool) -> None:
    root = Path(tempfile.mkdtemp(prefix="episalpha-smoke-"))
    data, labels = root / "data", root / "sealed-labels"
    labels.mkdir()
    for draft in sorted(LABEL_DRAFTS.glob("*.json")):
        shutil.copy(draft, labels / draft.name)
    settings = write_settings(root / "smoke.toml", data, labels)
    started = time.monotonic()

    seeded = cli(settings, "demo", "seed")
    check(seeded.returncode == 0, f"seed failed: {seeded.stderr}")
    print("ok seed")

    runs = {}
    for case in CASES:
        result = cli(settings, "research", "run", "--case", case, "--runtime", "fake")
        check(result.stdout.startswith(FIXTURE), f"{case}: output is not labelled a fixture")
        found = re.search(r"^run_id: (run-[0-9a-f]+)$", result.stdout, re.M)
        state = re.search(r"^state: (\w+)$", result.stdout, re.M)
        check(bool(found and state), f"{case}: no run ID or state in {result.stdout!r}")
        assert found and state
        check(result.returncode in (0, 5), f"{case}: exit {result.returncode}, {result.stdout}")
        runs[case] = found.group(1)
        print(f"ok run {case}: {runs[case]} {state.group(1)}")

    if inject_failure:  # self-test: an edited artifact must stop the smoke
        thesis = data / "runs" / runs["supported"] / "thesis.json"
        thesis.write_bytes(thesis.read_bytes().replace(b"412.0", b"999.0"))

    for run_id in runs.values():
        result = cli(settings, "replay", run_id, offline=True)
        check(result.returncode == 0, f"replay {run_id}: {result.stdout}{result.stderr}")
        check("no model or network calls" in result.stdout, f"replay {run_id}: not a saved replay")
    warm = time.monotonic()
    cli(settings, "replay", runs["supported"], offline=True)
    replay_seconds = time.monotonic() - warm
    print(f"ok replay ({len(runs)} runs, network blocked)")

    vault = root / "vault"
    for run_id in runs.values():
        result = cli(settings, "export", "obsidian", "--run", run_id, "--output", str(vault))
        check(result.returncode == 0, f"export {run_id}: {result.stdout}{result.stderr}")
    links = [
        (page, target)
        for page in vault.rglob("*.md")
        for target in re.findall(r"\[\[([^\]|#]+)", page.read_text())
    ]
    broken = [target for _, target in links if not (vault / target).is_file()]
    check(bool(links) and not broken, f"vault links unresolved: {broken[:5]}")
    print(f"ok export ({len(links)} links, all resolve)")

    compared = cli(settings, "experiment", "compare", "--campaign", "demo-v1", "--runtime", "fake")
    check(compared.returncode == 0, f"experiment: {compared.stdout}{compared.stderr}")
    report = re.search(r"^report: (.+)$", compared.stdout, re.M)
    decision = re.search(r"^decision: (\w+)", compared.stdout, re.M)
    check(bool(report and decision), f"experiment printed no report or decision: {compared.stdout}")
    assert report and decision
    print(f"ok experiment: {decision.group(1)}")

    hashes = backup(data, root / "backup")
    print(f"ok backup ({len(hashes)} files hashed)")
    restored = root / "restored"
    restore(root / "backup", restored)
    second = write_settings(root / "restored.toml", restored, labels)
    replayed = cli(second, "replay", runs["supported"], offline=True)
    check(replayed.returncode == 0, f"replay from the restored copy failed: {replayed.stdout}")
    print("ok restore (hashes verified; replay from the restored copy)")

    print(f"data root: {data}")
    print(f"vault: {vault}")
    print(f"report: {report.group(1)}")
    print(f"backup: {root / 'backup'}")
    print(f"replay after warm-up: {replay_seconds:.2f} s")
    print(f"total: {time.monotonic() - started:.1f} s")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--inject-failure", action="store_true", help="self-test: tamper an artifact, expect FAIL"
    )
    arguments = parser.parse_args()
    print(f"{FIXTURE}: every run below is scripted fixture output, not research")
    try:
        run(arguments.inject_failure)
    except SmokeFailure as failure:
        print(f"FAILED: {failure}")
        return 1
    print("smoke: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
