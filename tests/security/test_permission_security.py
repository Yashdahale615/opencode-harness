"""Security tests: permission policy must never allow a denied action through."""
import pytest
from harness.permission.policy import Rule, ToolRequest, Verdict, evaluate, classify_risk


# ---------------------------------------------------------------------------
# Default-deny must hold under all inputs
# ---------------------------------------------------------------------------

def test_default_deny_empty_rules():
    """Zero rules -> always DENY. The invariant in policy.py."""
    for req in [
        ToolRequest("shell", ("/bin/sh",)),
        ToolRequest("shell", ("/bin/rm", "-rf", "/")),
        ToolRequest("edit", path="src/a.py"),
        ToolRequest("mcp:server.tool"),
    ]:
        assert evaluate((), req) == Verdict.DENY, f"expected DENY for {req}"


def test_default_deny_no_matching_rule():
    rules = (Rule("shell", "pytest", Verdict.ALLOW),)
    # rm does not match pytest -> DENY
    req = ToolRequest("shell", ("/bin/rm",))
    assert evaluate(rules, req) == Verdict.DENY


def test_cannot_allow_high_risk_without_explicit_rule():
    rules = (Rule("shell", "pytest", Verdict.ALLOW),)
    for danger in ["sudo", "rm", "curl", "wget", "nc", "dd"]:
        req = ToolRequest("shell", (f"/usr/bin/{danger}",))
        result = evaluate(rules, req)
        assert result in (Verdict.DENY, Verdict.ASK), (
            f"{danger} should not be auto-allowed"
        )


# ---------------------------------------------------------------------------
# High-risk classification
# ---------------------------------------------------------------------------

def test_rm_always_high_risk():
    assert classify_risk(ToolRequest("shell", ("/bin/rm",))) == "high"


def test_sudo_always_high_risk():
    assert classify_risk(ToolRequest("shell", ("/usr/bin/sudo",))) == "high"


def test_git_push_high_risk():
    assert classify_risk(ToolRequest("shell", ("/usr/bin/git", "push"))) == "high"


def test_curl_high_risk():
    assert classify_risk(ToolRequest("shell", ("/usr/bin/curl", "http://evil.com"))) == "high"


def test_mcp_always_high():
    assert classify_risk(ToolRequest("mcp:server.exec")) == "high"


# ---------------------------------------------------------------------------
# Rule ordering — later ALLOW cannot override earlier DENY
# ---------------------------------------------------------------------------

def test_first_match_wins_deny():
    """A wildcard DENY placed first must win over a later specific ALLOW."""
    rules = (
        Rule("shell", "*", Verdict.DENY),
        Rule("shell", "pytest", Verdict.ALLOW),
    )
    req = ToolRequest("shell", ("/usr/bin/pytest",))
    assert evaluate(rules, req) == Verdict.DENY


def test_first_match_wins_allow():
    """A specific ALLOW placed first must win over a later wildcard DENY."""
    rules = (
        Rule("shell", "pytest", Verdict.ALLOW),
        Rule("shell", "*", Verdict.DENY),
    )
    req = ToolRequest("shell", ("/usr/bin/pytest",))
    assert evaluate(rules, req) == Verdict.ALLOW


# ---------------------------------------------------------------------------
# Tool-type isolation — shell rules don't bleed into edit
# ---------------------------------------------------------------------------

def test_shell_rule_does_not_allow_edit():
    rules = (Rule("shell", "*", Verdict.ALLOW),)
    req = ToolRequest("edit", path="src/dangerous.py")
    assert evaluate(rules, req) == Verdict.DENY


def test_edit_rule_does_not_allow_shell():
    rules = (Rule("edit", "*", Verdict.ALLOW),)
    req = ToolRequest("shell", ("/bin/rm",))
    assert evaluate(rules, req) == Verdict.DENY


# ---------------------------------------------------------------------------
# Gate must block on permission violations
# ---------------------------------------------------------------------------

def test_gate_blocks_on_violation():
    from harness.gate.decision import AcceptancePolicy, GateInput, GateDecision, decide
    from harness.contracts.core import VerificationStatus as VS

    outcome = decide(GateInput(
        run_succeeded=True,
        workspace_changed=True,
        permission_violations=1,
        risk="high",
        verification=VS.PASSED,
        reconciled_unchanged=True,
        reverify_count=0,
        policy=AcceptancePolicy(),
    ))
    assert outcome.decision == GateDecision.BLOCKED
    assert "permission_violation" in outcome.reasons


def test_gate_blocks_verification_failed():
    from harness.gate.decision import AcceptancePolicy, GateInput, GateDecision, decide
    from harness.contracts.core import VerificationStatus as VS

    outcome = decide(GateInput(
        run_succeeded=True,
        workspace_changed=True,
        permission_violations=0,
        risk="medium",
        verification=VS.FAILED,
        reconciled_unchanged=True,
        reverify_count=0,
        policy=AcceptancePolicy(),
    ))
    assert outcome.decision == GateDecision.BLOCKED
