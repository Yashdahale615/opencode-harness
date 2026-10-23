"""Unit tests for harness.workspace.snapshot and harness.workspace.paths."""
import os
import tempfile
from pathlib import Path

import pytest
from harness.workspace.snapshot import (
    Entry,
    diff,
    take_snapshot,
    workspace_fingerprint,
)
from harness.workspace.paths import PathEscape, resolve_inside


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------

def make_ws():
    tmp = Path(tempfile.mkdtemp())
    ws = tmp / "ws"
    ws.mkdir()
    return ws


def test_snapshot_empty_dir():
    ws = make_ws()
    snap = take_snapshot(ws)
    assert isinstance(snap, dict)
    assert len(snap) == 0


def test_snapshot_records_file():
    ws = make_ws()
    (ws / "hello.txt").write_text("hi")
    snap = take_snapshot(ws)
    assert "hello.txt" in snap
    e = snap["hello.txt"]
    assert e.kind == "file"
    assert e.size == 2


def test_snapshot_records_directory():
    ws = make_ws()
    (ws / "sub").mkdir()
    snap = take_snapshot(ws)
    assert "sub" in snap
    assert snap["sub"].kind == "dir"


def test_snapshot_excludes_git():
    ws = make_ws()
    (ws / ".git").mkdir()
    (ws / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    snap = take_snapshot(ws)
    assert not any(k.startswith(".git") for k in snap)


def test_workspace_fingerprint_stable():
    ws = make_ws()
    (ws / "a.py").write_text("x=1")
    snap = take_snapshot(ws)
    fp1 = workspace_fingerprint(snap)
    fp2 = workspace_fingerprint(snap)
    assert fp1 == fp2
    assert fp1.startswith("sha256:")


def test_workspace_fingerprint_changes_on_content():
    ws = make_ws()
    (ws / "a.py").write_text("x=1")
    snap1 = take_snapshot(ws)
    (ws / "a.py").write_text("x=2")
    snap2 = take_snapshot(ws)
    assert workspace_fingerprint(snap1) != workspace_fingerprint(snap2)


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------

def test_diff_added():
    before = {}
    after  = {"new.py": Entry("file", 0o644, 3, "sha256:abc")}
    d = diff(before, after)
    assert "new.py" in d.added
    assert not d.deleted
    assert not d.modified


def test_diff_deleted():
    e = Entry("file", 0o644, 3, "sha256:abc")
    d = diff({"gone.py": e}, {})
    assert "gone.py" in d.deleted


def test_diff_modified():
    before = {"f.py": Entry("file", 0o644, 1, "sha256:aaa")}
    after  = {"f.py": Entry("file", 0o644, 2, "sha256:bbb")}
    d = diff(before, after)
    assert "f.py" in d.modified


def test_diff_bool():
    e = Entry("file", 0o644, 3, "sha256:abc")
    assert not diff({"f": e}, {"f": e})
    assert diff({}, {"f": e})


# ---------------------------------------------------------------------------
# resolve_inside
# ---------------------------------------------------------------------------

def test_resolve_inside_ok():
    ws = make_ws()
    (ws / "src").mkdir()
    p = resolve_inside(ws, "src")
    # Use .resolve() on both to normalise short/long path forms on Windows
    assert ws.resolve() in p.resolve().parents or p.resolve() == ws.resolve() / "src"


def test_resolve_inside_escape():
    ws = make_ws()
    with pytest.raises(PathEscape):
        resolve_inside(ws, "../other")
