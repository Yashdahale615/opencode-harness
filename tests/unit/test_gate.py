"""Unit tests for harness.gate.decision and harness.gate.reconcile."""
import pytest
from harness.gate.decision import (
    AcceptancePolicy,
    GateDecision,
    GateInput,
    GateOutcome,
    GateState,
    decide,
)
from harness.contracts.core import GateDecision as GD, VerificationStatus as VS


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

P = AcceptancePolicy()


def make(
    *,
    run_succeeded=True,
    workspace_changed=True,
    permission_violations=0,
    risk="medium",
    verification=VS.PASSED,
    reconciled_unchanged=True,
    reverify_count=0,
    policy=None,
) -> GateOutcome:
    return decide(GateInput(
        run_succeeded=run_succeeded,
        workspace_changed=workspace_changed,
        permission_violations=permission_violations,
        risk=risk,
        verification=verification,
        reconciled_unchanged=reconciled_unchanged,
        reverify_count=reverify_count,
        policy=policy or P,
    ))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_happy_path():
    o = make()
    assert o.decision == GD.ALLOWED
    assert o.state == GateState.ALLOWED_VERIFIED
    assert "verified_and_reconciled" in o.reasons


def test_permission_violation_blocks():
    o = make(permission_violations=1)
    assert o.decision == GD.BLOCKED
    assert "permission_violation" in o.reasons


def test_run_failed_blocks():
    o = make(run_succeeded=False)
    assert o.decision == GD.BLOCKED
    assert "agent_run_failed" in o.reasons


def test_no_workspace_change_allows():
    o = make(workspace_changed=False)
    assert o.decision == GD.ALLOWED
    assert o.state == GateState.ALLOWED_NO_MUTATION


def test_no_trusted_check_asks_user():
    o = make(verification=None)
    assert o.decision == GD.ASK_USER


def test_no_trusted_check_low_risk_allowed_if_policy_set():
    pol = AcceptancePolicy(allow_unverified_low_risk=True)
    o = make(verification=None, risk="low", policy=pol)
    assert o.decision == GD.ALLOWED
    assert o.state == GateState.ALLOWED_NOT_VERIFIED


def test_verification_failed_blocks():
    o = make(verification=VS.FAILED)
    assert o.decision == GD.BLOCKED
    assert "verification_failed" in o.reasons


def test_verification_unavailable_asks_user():
    o = make(verification=VS.UNAVAILABLE)
    assert o.decision == GD.ASK_USER
    assert o.state == GateState.UNVERIFIABLE


def test_reconciliation_missing_blocks():
    o = make(reconciled_unchanged=None)
    assert o.decision == GD.BLOCKED
    assert "reconciliation_missing" in o.reasons


def test_state_changed_during_verification():
    o = make(reconciled_unchanged=False, reverify_count=0)
    assert o.state == GateState.REVERIFY
    assert o.decision == GD.BLOCKED


def test_state_changed_exceeds_reverify():
    pol = AcceptancePolicy(max_reverify=2)
    o = make(reconciled_unchanged=False, reverify_count=2, policy=pol)
    assert "verification_not_stable" in o.reasons


def test_decide_is_pure():
    """Calling decide() twice with same input must return equal results."""
    inp = GateInput(
        run_succeeded=True,
        workspace_changed=True,
        permission_violations=0,
        risk="low",
        verification=VS.PASSED,
        reconciled_unchanged=True,
        reverify_count=0,
        policy=P,
    )
    assert decide(inp) == decide(inp)


# ---------------------------------------------------------------------------
# Reconcile
# ---------------------------------------------------------------------------

def test_reconcile_unchanged():
    from harness.gate.reconcile import reconcile
    snap = {"file.py": object()}  # same reference = no diff
    # Use real Entry objects
    from harness.workspace.snapshot import take_snapshot, Entry
    e = Entry("file", 0o644, 5, "sha256:abc")
    s = {"file.py": e}
    r = reconcile(s, s, 1)
    assert r.unchanged is True
    assert r.mutation_revision == 1


def test_reconcile_changed():
    from harness.gate.reconcile import reconcile
    from harness.workspace.snapshot import Entry
    before = {"file.py": Entry("file", 0o644, 5, "sha256:abc")}
    after  = {"file.py": Entry("file", 0o644, 6, "sha256:def")}
    r = reconcile(before, after, 1)
    assert r.unchanged is False
    assert r.mutation_revision == 2
    assert "file.py" in r.changed_paths
