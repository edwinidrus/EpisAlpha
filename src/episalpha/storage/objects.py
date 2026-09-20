"""Content-addressed store for original source bytes (plan M2-T02).

Original payloads are the ground truth: everything else in the system is derived from them and
can be rebuilt, but if the bytes are lost or quietly altered, nothing downstream can be trusted
again. So this store is append-only by construction — an address *is* the SHA-256 of the
content, writes are atomic, and putting different bytes at an existing address is impossible
rather than merely discouraged.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

from episalpha.contracts.errors import EpisAlphaError, ErrorCode


class ObjectIntegrityError(EpisAlphaError):
    """Stored bytes do not match the hash they are filed under."""

    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.INTEGRITY_ERROR, message)


def content_hash(payload: bytes) -> str:
    """The address of some bytes: lowercase SHA-256 hex."""
    return hashlib.sha256(payload).hexdigest()


class ObjectStore:
    """A content-addressed blob store under one directory.

    Objects are sharded by the first two hex characters, which keeps any single directory from
    growing to an awkward size.
    """

    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, digest: str) -> Path:
        return self.root / digest[:2] / digest

    def put(self, payload: bytes) -> str:
        """Store bytes and return their address.

        Identical bytes deduplicate: the second write is a no-op, not a rewrite. Different bytes
        always get a different address, so an existing object is never replaced. The write goes
        to a temporary file in the same directory and is then renamed, so a crash leaves either
        the complete object or nothing — never a truncated one.
        """
        digest = content_hash(payload)
        destination = self._path(digest)
        if destination.exists():
            return digest

        destination.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(dir=destination.parent, suffix=".partial")
        try:
            with os.fdopen(handle, "wb") as file:
                file.write(payload)
                file.flush()
                os.fsync(file.fileno())
            # os.replace is atomic within a filesystem. A concurrent writer storing the same
            # bytes is harmless: both produce identical content at the same address.
            os.replace(temporary, destination)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise
        return digest

    def get(self, digest: str) -> bytes:
        """Read an object back, verifying it still hashes to its own address.

        Verification is not paranoia: silent corruption here would turn every downstream
        quotation check into a check against the wrong text.
        """
        path = self._path(digest)
        if not path.exists():
            raise ObjectIntegrityError(f"no object stored at {digest}")
        payload = path.read_bytes()
        actual = content_hash(payload)
        if actual != digest:
            raise ObjectIntegrityError(
                f"object at {digest} hashes to {actual}; the stored bytes have changed"
            )
        return payload

    def exists(self, digest: str) -> bool:
        return self._path(digest).exists()

    def addresses(self) -> Iterator[str]:
        """Every stored address, in sorted order."""
        if not self.root.exists():
            return
        for shard in sorted(self.root.iterdir()):
            if shard.is_dir():
                yield from sorted(path.name for path in shard.iterdir() if path.is_file())
