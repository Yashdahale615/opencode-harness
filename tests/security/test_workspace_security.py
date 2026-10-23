"""Security tests: workspace snapshot and path escape prevention."""
import os
import tempfile
from pathlib import Path

import pytest
from harness.workspace.paths import PathEscape, resolve_inside
from harness.workspace.snapshot import SnapshotError, take_snapshot


def make_ws():
    tmp = Path(tempfile.mkdtemp())
    ws = tmp / "ws"
    ws.mkdir()
    return ws


def test_path_escape_via_dotdot():
    ws = make_ws()
    with pytest.raises(PathEscape):
        resolve_inside(ws, "../etc/passwd")


def test_path_escape_via_absolute():
    ws = make_ws()
    with pytest.raises(PathEscape):
        resolve_inside(ws, "/etc/passwd")


def test_symlink_not_followed_in_snapshot():
    """A symlink inside the workspace must be recorded as 'symlink', not
    followed to read the target (TOCTOU-safe).
    Skipped on Windows where symlink creation requires elevated privileges."""
    import sys
    if sys.platform == "win32":
        pytest.skip("symlink creation may require elevated privileges on Windows")
    ws = make_ws()
    (ws / "real.txt").write_text("secret")
    os.symlink("/etc/passwd", ws / "link.txt")
    snap = take_snapshot(ws)
    assert snap["link.txt"].kind == "symlink"
    assert snap["link.txt"].digest.startswith("link:")


def test_git_dir_excluded():
    ws = make_ws()
    (ws / ".git").mkdir()
    (ws / ".git" / "config").write_text("[core]")
    snap = take_snapshot(ws)
    assert not any(k.startswith(".git") for k in snap)


def test_harness_dir_excluded():
    ws = make_ws()
    (ws / ".harness").mkdir()
    (ws / ".harness" / "trace.jsonl").write_text("{}")
    snap = take_snapshot(ws)
    # .harness is NOT in EXCLUDED_TOP by default (only .git, __pycache__, node_modules)
    # but the controller stores output there; this test documents current behaviour.
    # If .harness is excluded in future, update this assertion.
    # Currently: .harness IS snapshotted
    pass   # no assertion — just verify it doesn't raise


def test_fingerprint_includes_all_files():
    ws = make_ws()
    (ws / "a.py").write_text("x=1")
    (ws / "b.py").write_text("y=2")
    from harness.workspace.snapshot import workspace_fingerprint
    snap = take_snapshot(ws)
    fp = workspace_fingerprint(snap)
    assert fp.startswith("sha256:")
    # Adding a file changes the fingerprint
    (ws / "c.py").write_text("z=3")
    snap2 = take_snapshot(ws)
    fp2 = workspace_fingerprint(snap2)
    assert fp != fp2
