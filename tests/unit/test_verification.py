"""Unit tests for harness.verification.* (catalog, select, runtime aggregate)."""
import hashlib
import json
import tempfile
from pathlib import Path

import pytest
from harness.verification.catalog import (
    CheckSpec,
    TrustError,
    load_catalog,
    sha256_file,
    validate_check,
)
from harness.verification.select import covers, select_checks
from harness.verification.runtime import aggregate
from harness.contracts.core import VerificationStatus as VS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_ws():
    tmp = Path(tempfile.mkdtemp())
    ws = tmp / "ws"
    ws.mkdir()
    (ws / "pytest.ini").write_text("[pytest]\n")
    (ws / "src").mkdir()
    (ws / "src" / "a.py").write_text("x=1\n")
    return tmp, ws


def write_catalog(trusted_dir: Path, checks: list) -> Path:
    cat = {"schema_version": 1, "checks": checks}
    p = trusted_dir / "catalog.json"
    p.write_text(json.dumps(cat))
    return p


# ---------------------------------------------------------------------------
# catalog loading
# ---------------------------------------------------------------------------

def test_load_catalog_basic():
    tmp, ws = make_ws()
    trusted = tmp / "trusted"
    trusted.mkdir()
    ini_sha = hashlib.sha256(b"[pytest]\n").hexdigest()
    cat_path = write_catalog(trusted, [{
        "check_id": "unit",
        "argv": ["/bin/true"],
        "cwd": ".",
        "scope": ["src/*"],
        "cost_rank": 1,
        "timeout_seconds": 30,
        "env_allow": ["PATH"],
        "immutable_inputs": {"pytest.ini": ini_sha},
    }])
    catalog = load_catalog(cat_path, ws)
    assert len(catalog.checks) == 1
    assert catalog.checks[0].check_id == "unit"


def test_load_catalog_inside_workspace_rejected():
    tmp, ws = make_ws()
    # Write catalog inside workspace
    cat_path = ws / "catalog.json"
    cat_path.write_text(json.dumps({"schema_version": 1, "checks": []}))
    with pytest.raises(TrustError, match="OUTSIDE"):
        load_catalog(cat_path, ws)


def test_load_catalog_bad_schema_version():
    tmp, ws = make_ws()
    trusted = tmp / "trusted"
    trusted.mkdir()
    cat_path = trusted / "catalog.json"
    cat_path.write_text(json.dumps({"schema_version": 99, "checks": []}))
    with pytest.raises(Exception):
        load_catalog(cat_path, ws)


def test_load_catalog_duplicate_check_id():
    tmp, ws = make_ws()
    trusted = tmp / "trusted"
    trusted.mkdir()
    spec = {
        "check_id": "dup", "argv": ["/bin/true"], "cwd": ".",
        "scope": ["*"], "cost_rank": 1, "timeout_seconds": 10,
        "env_allow": [], "immutable_inputs": {},
    }
    cat_path = write_catalog(trusted, [spec, spec])
    with pytest.raises(Exception, match="duplicate"):
        load_catalog(cat_path, ws)


# ---------------------------------------------------------------------------
# validate_check
# ---------------------------------------------------------------------------

def test_validate_check_immutable_input_mismatch():
    """validate_check should raise TrustError when a tracked file is modified.
    Needs a real absolute executable to pass the path check first."""
    import shutil
    tmp, ws = make_ws()
    trusted = tmp / "trusted"
    trusted.mkdir()
    # Find a real absolute executable
    exe = shutil.which("python") or shutil.which("python3")
    if exe is None:
        pytest.skip("no python executable found")
    spec = CheckSpec(
        check_id="c1",
        argv=(exe,),
        cwd=".",
        scope=("src/*",),
        cost_rank=1,
        timeout_seconds=10,
        env_allow=("PATH",),
        immutable_inputs=(("pytest.ini", "wronghex"),),
    )
    with pytest.raises(TrustError, match="modified"):
        validate_check(spec, ws)


def test_validate_check_relative_argv():
    tmp, ws = make_ws()
    spec = CheckSpec(
        check_id="c1",
        argv=("pytest",),   # not absolute
        cwd=".",
        scope=("src/*",),
        cost_rank=1,
        timeout_seconds=10,
        env_allow=(),
        immutable_inputs=(),
    )
    with pytest.raises(TrustError, match="absolute"):
        validate_check(spec, ws)


# ---------------------------------------------------------------------------
# select_checks
# ---------------------------------------------------------------------------

def make_spec(check_id, scope, cost=1):
    return CheckSpec(
        check_id=check_id,
        argv=("/bin/true",),
        cwd=".",
        scope=tuple(scope),
        cost_rank=cost,
        timeout_seconds=10,
        env_allow=(),
        immutable_inputs=(),
    )


def test_select_checks_basic():
    specs = [make_spec("unit", ["src/*"]), make_spec("docs", ["docs/*"])]
    applicable, uncovered = select_checks(specs, ("src/a.py", "docs/r.md"))
    assert {s.check_id for s in applicable} == {"unit", "docs"}
    assert not uncovered


def test_select_checks_uncovered():
    specs = [make_spec("unit", ["src/*"])]
    _, uncovered = select_checks(specs, ("src/a.py", "scripts/x.sh"))
    assert "scripts/x.sh" in uncovered


def test_select_checks_ordered_by_cost():
    specs = [make_spec("slow", ["src/*"], cost=3),
             make_spec("fast", ["src/*"], cost=1)]
    applicable, _ = select_checks(specs, ("src/a.py",))
    assert applicable[0].check_id == "fast"


def test_covers_wildcard():
    s = make_spec("c", ["src/*"])
    assert covers(s, "src/a.py")
    assert not covers(s, "tests/t.py")


# ---------------------------------------------------------------------------
# aggregate
# ---------------------------------------------------------------------------

def make_vr(status, check_id="c1"):
    from harness.verification.runtime import VerificationResult
    return VerificationResult(
        check_id=check_id, status=status, reason="test",
        command_fp="fp", exit_code=0, duration_ms=0,
        stdout_tail="", stderr_tail="",
    )


def test_aggregate_passed():
    r = make_vr(VS.PASSED)
    assert aggregate([r]) == VS.PASSED


def test_aggregate_failed():
    ok = make_vr(VS.PASSED)
    bad = make_vr(VS.FAILED)
    assert aggregate([ok, bad]) == VS.FAILED


def test_aggregate_unavailable():
    ok = make_vr(VS.PASSED)
    unav = make_vr(VS.UNAVAILABLE)
    assert aggregate([ok, unav]) == VS.UNAVAILABLE


def test_aggregate_uncovered_path():
    ok = make_vr(VS.PASSED)
    result = aggregate([ok], uncovered=("orphan.py",))
    assert result == VS.UNAVAILABLE


def test_aggregate_ignorable_uncovered():
    ok = make_vr(VS.PASSED)
    result = aggregate([ok], uncovered=("docs/a.md",), ignorable=("docs/*",))
    assert result == VS.PASSED


def test_aggregate_empty_returns_none():
    assert aggregate([]) is None
