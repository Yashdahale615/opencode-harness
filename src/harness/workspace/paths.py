"""harness/workspace/paths.py - symlink-safe path handling."""
from __future__ import annotations

import os
from pathlib import Path


class PathEscape(PermissionError):
    pass


def resolve_inside(root: Path, candidate: str) -> Path:
    """Cheap pre-check (advisory only): resolves symlinks, must stay in root."""
    root_r = root.resolve(strict=True)
    p = (root_r / candidate).resolve(strict=False)
    if p != root_r and root_r not in p.parents:
        raise PathEscape(f"{candidate!r} escapes the workspace")
    return p


def open_beneath(root_fd: int, rel: str, flags: int = os.O_RDONLY) -> int:
    """Authoritative open: walk component by component with O_NOFOLLOW so a
    symlink swapped in after the pre-check cannot redirect us (TOCTOU).

    On Windows, dir_fd and O_NOFOLLOW are not available; the function raises
    NotImplementedError to signal that the advisory resolve_inside() should
    be used instead."""
    import sys
    if sys.platform == "win32":
        raise NotImplementedError("open_beneath is not supported on Windows")
    parts = [p for p in rel.split("/") if p not in ("", ".")]
    if ".." in parts:
        raise PathEscape("'..' is not allowed")
    fd = os.dup(root_fd)
    try:
        for i, part in enumerate(parts):
            last = i == len(parts) - 1
            mode = flags if last else os.O_RDONLY | os.O_DIRECTORY
            nxt = os.open(part, mode | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = nxt
        return fd
    except BaseException:
        os.close(fd)
        raise
