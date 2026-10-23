"""harness/verification/runtime.py - run trusted checks, map to a status."""
from __future__ import annotations

import os
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path

from harness.contracts.core import ContractError, VerificationStatus as VS
from harness.execution.process import RunLimits, run_contained
from harness.verification.catalog import CheckSpec, TrustError, validate_check


@dataclass(frozen=True)
class VerificationResult:
    check_id: str
    status: VS
    reason: str
    command_fp: str
    exit_code: int | None
    duration_ms: int
    stdout_tail: str
    stderr_tail: str


def run_check(spec: CheckSpec, workspace: Path) -> VerificationResult:
    def result(status, reason, fp="", r=None):
        return VerificationResult(
            spec.check_id, status, reason, fp,
            r.exit_code if r else None, r.duration_ms if r else 0,
            r.stdout_tail if r else "", r.stderr_tail if r else "")
    try:
        fp = validate_check(spec, workspace)      # identity + trust first
    except (TrustError, ContractError, OSError) as exc:
        return result(VS.UNAVAILABLE, f"trust_failure: {exc}")
    env = {k: os.environ[k] for k in spec.env_allow if k in os.environ}
    try:
        r = run_contained(list(spec.argv), cwd=str(workspace / spec.cwd),
                          env=env,
                          limits=RunLimits(wall_seconds=spec.timeout_seconds))
    except (OSError, ValueError) as exc:
        return result(VS.UNAVAILABLE, f"launch_failure: {exc}", fp)
    if r.timed_out:
        return result(VS.FAILED, "timeout", fp, r)
    if r.exit_code == 0:
        return result(VS.PASSED, "exit_0", fp, r)
    return result(VS.FAILED, f"exit_{r.exit_code}", fp, r)


def aggregate(results, uncovered=(), ignorable=()):
    """None means 'no trusted check applied'. Any FAILED wins, then any
    UNAVAILABLE or uncovered path; only full coverage can PASS."""
    left = [p for p in uncovered
            if not any(fnmatchcase(p, g) for g in ignorable)]
    if not results:
        return None
    statuses = {r.status for r in results}
    if VS.FAILED in statuses:
        return VS.FAILED
    if VS.UNAVAILABLE in statuses or left:
        return VS.UNAVAILABLE
    return VS.PASSED
