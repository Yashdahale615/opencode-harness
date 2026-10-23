"""harness/verification/catalog.py - trusted verification catalog."""
from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from harness.contracts.core import (ContractError, exact_keys, fingerprint,
                                    safe_id)


class TrustError(RuntimeError):
    """Something we would have to trust is not trustworthy."""


@dataclass(frozen=True)
class CheckSpec:
    check_id: str
    argv: tuple[str, ...]            # argv[0] is an ABSOLUTE path
    cwd: str                         # relative to workspace, e.g. "."
    scope: tuple[str, ...]           # globs of paths this check covers
    cost_rank: int                   # lower runs first
    timeout_seconds: int
    env_allow: tuple[str, ...]
    immutable_inputs: tuple[tuple[str, str], ...]   # (relpath, sha256 hex)


@dataclass(frozen=True)
class Catalog:
    fingerprint: str
    checks: tuple[CheckSpec, ...]


def _is_inside(child: Path, parent: Path) -> bool:
    return child == parent or parent in child.parents


def assert_trusted_ancestry(path: Path) -> None:
    """Every ancestor must be owned by root/us and not group/world writable.
    On Windows this check is skipped (the OS handles permissions differently)."""
    import sys
    if sys.platform == "win32":
        return  # Windows lacks POSIX ownership / mode bits
    me = os.geteuid()
    for d in (path, *path.parents):
        st = d.stat()
        if st.st_mode & 0o022:
            raise TrustError(f"{d} is group/world writable")
        if st.st_uid not in (0, me):
            raise TrustError(f"{d} has untrusted owner {st.st_uid}")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def load_catalog(catalog_path: Path, workspace: Path) -> Catalog:
    real = catalog_path.resolve(strict=True)
    ws = workspace.resolve(strict=True)
    if _is_inside(real, ws):
        raise TrustError("catalog must live OUTSIDE the workspace")
    assert_trusted_ancestry(real)
    raw = real.read_bytes()                  # read ONCE; parse those bytes
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ContractError(f"catalog: invalid JSON: {exc}") from None
    exact_keys(doc, ["schema_version", "checks"], where="catalog")
    if doc["schema_version"] != 1:
        raise ContractError("catalog: unsupported schema_version")
    checks, seen = [], set()
    for i, c in enumerate(doc["checks"]):
        exact_keys(c, ["check_id", "argv", "cwd", "scope", "cost_rank",
                       "timeout_seconds", "env_allow", "immutable_inputs"],
                   where=f"checks[{i}]")
        cid = safe_id(c["check_id"], f"checks[{i}].check_id")
        if cid in seen:
            raise ContractError(f"duplicate check_id {cid}")
        seen.add(cid)
        checks.append(CheckSpec(
            cid, tuple(c["argv"]), c["cwd"], tuple(c["scope"]),
            int(c["cost_rank"]), int(c["timeout_seconds"]),
            tuple(c["env_allow"]),
            tuple((p, h) for p, h in sorted(c["immutable_inputs"].items()))))
    return Catalog(fingerprint(doc, "catalog/v1"), tuple(checks))


def validate_check(spec: CheckSpec, workspace: Path) -> str:
    """Identity validation. Returns the command fingerprint or raises."""
    ws = workspace.resolve(strict=True)
    exe = Path(spec.argv[0])
    if not exe.is_absolute():
        raise TrustError(f"{spec.check_id}: executable must be absolute")
    exe = exe.resolve(strict=True)
    if _is_inside(exe, ws):
        raise TrustError(f"{spec.check_id}: executable is inside workspace")
    if not (stat.S_ISREG(exe.stat().st_mode) and os.access(exe, os.X_OK)):
        raise TrustError(f"{spec.check_id}: not an executable file")
    assert_trusted_ancestry(exe)
    cwd = (ws / spec.cwd).resolve(strict=True)
    if not _is_inside(cwd, ws):
        raise TrustError(f"{spec.check_id}: cwd escapes workspace")
    for rel, want in spec.immutable_inputs:
        got = sha256_file(ws / rel)          # config the agent may not weaken
        if got != want:
            raise TrustError(f"{spec.check_id}: {rel} was modified")
    return fingerprint({"argv": list(spec.argv), "cwd": spec.cwd,
                        "exe_sha256": sha256_file(exe),
                        "env_allow": sorted(spec.env_allow),
                        "inputs": dict(spec.immutable_inputs)}, "command/v1")
