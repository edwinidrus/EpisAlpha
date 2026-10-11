"""Run artifacts: what a run produced, hashed and indexed (plan sections 3.6-3.7, M4-T01).

Each run owns ``<data_root>/runs/<run_id>/``. Every artifact is canonical JSON (sorted keys, no
whitespace), written atomically, and its SHA-256 goes into ``index.json`` next to the run's
provenance: trace ID, snapshot hash, harness and skill-set hashes, runtime label. Replay
(M4-T03) re-reads artifacts through :meth:`RunArtifacts.read`, which refuses any file whose
hash no longer matches the index: tampering is an ``INTEGRITY_ERROR``, never silently accepted.

Stage payloads are kept per attempt, before any repair, because M6's numeric-correctness metric
compares what the model proposed with what the host recomputed.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from episalpha.contracts.errors import EpisAlphaError, ErrorCode
from episalpha.contracts.research import RunRecord
from episalpha.evidence.snapshots import verify_snapshot
from episalpha.observability import SpanKind, span
from episalpha.storage.repository import Repository

_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]*(/[a-z0-9][a-z0-9_-]*)*$")
INDEX = "index.json"


class ArtifactIntegrityError(EpisAlphaError):
    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.INTEGRITY_ERROR, message)


def canonical(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


class RunArtifacts:
    """The artifact directory of one run. Names are fixed by the runner, never by a model."""

    def __init__(self, root: Path, run_id: str) -> None:
        self.directory = root / run_id
        self.hashes: dict[str, str] = {}
        self.provenance: dict[str, Any] = {}
        index = self.directory / INDEX
        if index.exists():
            loaded = json.loads(index.read_text())
            self.hashes = dict(loaded.pop("artifacts", {}))
            self.provenance = loaded

    def _path(self, name: str) -> Path:
        if not _NAME.match(name):
            raise ValueError(f"{name!r} is not a valid artifact name")
        return self.directory / f"{name}.json"

    def write(self, name: str, payload: Any) -> str:
        data = canonical(payload)
        _atomic_write(self._path(name), data)
        digest = hashlib.sha256(data).hexdigest()
        self.hashes[name] = digest
        # The index follows every write, so a crash mid-run still leaves a verifiable record
        # of everything saved so far (recovery reuses it).
        self.write_index()
        return digest

    def write_index(self, **provenance: Any) -> str:
        """Write ``index.json``: every artifact's hash plus the run's provenance."""
        self.provenance.update(provenance)
        data = canonical({"artifacts": dict(sorted(self.hashes.items())), **self.provenance})
        _atomic_write(self.directory / INDEX, data)
        return hashlib.sha256(data).hexdigest()

    def index(self) -> dict[str, Any]:
        return json.loads((self.directory / INDEX).read_text())  # type: ignore[no-any-return]

    def read(self, name: str) -> Any:
        """Read an artifact, verifying it against the index first."""
        expected = self.hashes.get(name)
        if expected is None:
            raise ArtifactIntegrityError(f"artifact {name!r} is not in the run's index")
        data = self._path(name).read_bytes()
        actual = hashlib.sha256(data).hexdigest()
        if actual != expected:
            raise ArtifactIntegrityError(
                f"artifact {name!r} hashes to {actual[:12]}..., the index says {expected[:12]}..."
            )
        return json.loads(data)

    def verify(self) -> list[str]:
        """Names of artifacts that are missing or no longer match the index."""
        broken = []
        for name, expected in sorted(self.hashes.items()):
            path = self._path(name)
            if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                broken.append(name)
        return broken


# --- replay ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class ReplayView:
    """A finished run as it was saved. Built from artifacts alone: no model, no network."""

    record: RunRecord
    index: dict[str, Any]
    manifest: dict[str, Any]
    records: dict[str, Any]
    validation: dict[str, Any] | None
    thesis: dict[str, Any] | None
    stages: list[dict[str, Any]]
    proposals: list[Any]
    verified: int


def replay(repo: Repository, runs_root: Path, run_id: str) -> ReplayView:
    """Re-open a run from its saved artifacts, verifying every hash along the way.

    Chain of trust: every artifact must match ``index.json``; the manifest and the thesis must
    also equal the canonical records in SQLite, so editing an artifact *and* its index entry is
    still caught. Later evidence or assessments change nothing here: replay reads what the run
    saved, not today's database.
    """
    with span("replay", SpanKind.CHAIN, **{"episalpha.run_id": run_id}) as current:
        record = repo.get_run(run_id)
        if record is None:
            raise EpisAlphaError(ErrorCode.INVALID_REQUEST, f"run {run_id!r} does not exist")
        artifacts = RunArtifacts(runs_root, run_id)
        if not artifacts.hashes:
            raise ArtifactIntegrityError(f"run {run_id!r} has no artifact index")
        broken = artifacts.verify()
        if broken:
            raise ArtifactIntegrityError(f"artifacts no longer match their hashes: {broken}")
        index = artifacts.index()
        manifest = artifacts.read("manifest")
        snapshot = repo.get_snapshot(manifest["snapshot_id"])
        if snapshot is None or snapshot.model_dump(mode="json") != manifest:
            raise ArtifactIntegrityError("manifest artifact differs from the canonical snapshot")
        if not verify_snapshot(snapshot) or index.get("snapshot_hash") != snapshot.snapshot_hash:
            raise ArtifactIntegrityError("snapshot hash does not verify")
        thesis = artifacts.read("thesis") if "thesis" in artifacts.hashes else None
        if thesis is not None:
            canonical_thesis = repo.get_thesis(thesis["thesis_id"])
            if canonical_thesis is None or canonical_thesis.model_dump(mode="json") != thesis:
                raise ArtifactIntegrityError("thesis artifact differs from the canonical thesis")
        if index.get("state") != record.state.value:
            raise ArtifactIntegrityError("index state differs from the canonical run state")
        stages = [
            artifacts.read(name)
            for name in sorted(artifacts.hashes, key=_stage_order)
            if name.startswith("stages/")
        ]
        view = ReplayView(
            record=record,
            index=index,
            manifest=manifest,
            records=artifacts.read("records"),
            validation=artifacts.read("validation") if "validation" in artifacts.hashes else None,
            thesis=thesis,
            stages=stages,
            proposals=artifacts.read("proposals") if "proposals" in artifacts.hashes else [],
            verified=len(artifacts.hashes),
        )
        current.set_attribute("episalpha.verified_artifacts", view.verified)
    return view


_STAGE_ORDER = {"researching": 0, "critiquing": 1, "synthesizing": 2}


def _stage_order(name: str) -> tuple[int, int]:
    stage, _, attempt = name.removeprefix("stages/").rpartition("-")
    return (_STAGE_ORDER.get(stage, 9), int(attempt) if attempt.isdigit() else 0)
