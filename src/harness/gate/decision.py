"""harness/gate/decision.py - the gate: a PURE function of its inputs."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from harness.contracts.core import GateDecision, VerificationStatus


class GateState(str, Enum):
    RUN_FAILED = "run_failed"
    ALLOWED_NO_MUTATION = "allowed_no_mutation"
    ALLOWED_NOT_VERIFIED = "allowed_not_verified"
    BLOCKED = "blocked"
    UNVERIFIABLE = "unverifiable"
    REVERIFY = "reverify"
    ALLOWED_VERIFIED = "allowed_verified"


@dataclass(frozen=True)
class AcceptancePolicy:
    allow_unverified_low_risk: bool = False
    max_reverify: int = 2


@dataclass(frozen=True)
class GateInput:
    run_succeeded: bool
    workspace_changed: bool
    permission_violations: int
    risk: str                                   # low | medium | high
    verification: VerificationStatus | None     # None = no trusted check
    reconciled_unchanged: bool | None           # None = not reconciled yet
    reverify_count: int
    policy: AcceptancePolicy


@dataclass(frozen=True)
class GateOutcome:
    state: GateState
    decision: GateDecision
    reasons: tuple[str, ...]


def _out(state, decision, *reasons) -> GateOutcome:
    return GateOutcome(state, decision, tuple(reasons))


def decide(g: GateInput) -> GateOutcome:
    B, A, Q = GateDecision.BLOCKED, GateDecision.ALLOWED, GateDecision.ASK_USER
    if g.permission_violations:
        return _out(GateState.BLOCKED, B, "permission_violation")
    if not g.run_succeeded:
        return _out(GateState.RUN_FAILED, B, "agent_run_failed")
    if not g.workspace_changed:
        return _out(GateState.ALLOWED_NO_MUTATION, A, "no_mutation")
    if g.verification is None:                  # nothing trusted can check it
        if g.policy.allow_unverified_low_risk and g.risk == "low":
            return _out(GateState.ALLOWED_NOT_VERIFIED, A, "unverified_low_risk")
        return _out(GateState.ALLOWED_NOT_VERIFIED, Q, "no_trusted_check")
    if g.verification is VerificationStatus.FAILED:
        return _out(GateState.BLOCKED, B, "verification_failed")
    if g.verification is VerificationStatus.UNAVAILABLE:
        return _out(GateState.UNVERIFIABLE, Q, "verification_unavailable")
    if g.reconciled_unchanged is None:          # PASSED but never reconciled
        return _out(GateState.BLOCKED, B, "reconciliation_missing")
    if not g.reconciled_unchanged:
        if g.reverify_count >= g.policy.max_reverify:
            return _out(GateState.BLOCKED, B, "verification_not_stable")
        return _out(GateState.REVERIFY, B, "state_changed_during_verification")
    return _out(GateState.ALLOWED_VERIFIED, A, "verified_and_reconciled")
