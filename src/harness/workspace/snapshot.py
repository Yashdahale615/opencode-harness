"""harness/workspace/snapshot.py - before/after snapshots and diffs."""
from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from harness.contracts.core import fingerprint

EXCLUDED_TOP = frozenset({".git", ".harness", "__pycache__", "node_modules"})


class SnapshotError(RuntimeError):
    """Snapshot could not be taken faithfully -> caller must fail closed."""


@dataclass(frozen=True)
class Entry:
    kind: str      # file | dir | symlink | other
    mode: int
    size: int
    digest: str    # sha256 (file), "link:<target>" (symlink), "" otherwise


def _hash_file(path: str) -> str:
    h = hashlib.sha256()
    # O_NOFOLLOW and O_CLOEXEC are POSIX; fall back to simple open on Windows
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    try:
        fd = os.open(path, flags)
    except OSError as exc:      # includes ELOOP if swapped for a symlink
        raise SnapshotError(f"cannot read {path}: {exc}") from exc
    with os.fdopen(fd, "rb") as fh:
        while chunk := fh.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def take_snapshot(root: Path) -> dict[str, Entry]:
    root_s = os.path.realpath(root)
    out: dict[str, Entry] = {}
    stack = [""]
    while stack:
        rel_dir = stack.pop()
        with os.scandir(os.path.join(root_s, rel_dir)) as it:
            for de in it:
                if not rel_dir and de.name in EXCLUDED_TOP:
                    continue
                rel = f"{rel_dir}/{de.name}" if rel_dir else de.name
                st = de.stat(follow_symlinks=False)   # lstat: never follow
                mode = stat.S_IMODE(st.st_mode)
                if stat.S_ISLNK(st.st_mode):
                    out[rel] = Entry("symlink", mode, 0,
                                     "link:" + os.readlink(de.path))
                elif stat.S_ISDIR(st.st_mode):
                    out[rel] = Entry("dir", mode, 0, "")
                    stack.append(rel)
                elif stat.S_ISREG(st.st_mode):
                    out[rel] = Entry("file", mode, st.st_size,
                                     _hash_file(de.path))
                else:
                    out[rel] = Entry("other", mode, 0, "")
    return out


@dataclass(frozen=True)
class Diff:
    added: tuple[str, ...]
    modified: tuple[str, ...]
    deleted: tuple[str, ...]

    @property
    def changed(self) -> tuple[str, ...]:
        return tuple(sorted({*self.added, *self.modified, *self.deleted}))

    def __bool__(self) -> bool:
        return bool(self.changed)


def diff(before: dict[str, Entry], after: dict[str, Entry]) -> Diff:
    b, a = set(before), set(after)
    return Diff(
        added=tuple(sorted(a - b)),
        deleted=tuple(sorted(b - a)),
        modified=tuple(sorted(p for p in a & b if before[p] != after[p])),
    )


def workspace_fingerprint(snap: dict[str, Entry]) -> str:
    payload = {p: [e.kind, e.mode, e.size, e.digest]
               for p, e in sorted(snap.items())}
    return fingerprint(payload, "workspace/v1")
