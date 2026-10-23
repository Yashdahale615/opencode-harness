"""Security tests: receipt cannot be forged or applied to a different workspace."""
import pytest
from harness.contracts.core import ContractError, GateDecision, now_ts
from harness.evidence.receipt import Evidence, build_receipt, verify_receipt


def make_receipt(ws_fp="sha256:workspace1", decision=GateDecision.ALLOWED):
    e = Evidence(
        evidence_id="ev-sec",
        kind="verification",
        mutation_revision=1,
        workspace_fp=ws_fp,
        payload={"status": "passed"},
        produced_at=now_ts(),
    )
    return build_receipt(
        job_id="job-sec",
        session_id="s-sec",
        decision=decision,
        evidence=[e],
        catalog_fp="sha256:cat",
        command_fps=["sha256:cmd"],
        workspace_fp=ws_fp,
        policy_fp="sha256:pol",
        mutation_revision=1,
    )


def test_valid_receipt_accepted():
    r = make_receipt()
    verify_receipt(r, current_workspace_fp="sha256:workspace1")


def test_wrong_workspace_rejected():
    r = make_receipt("sha256:workspace1")
    with pytest.raises(ContractError, match="current workspace"):
        verify_receipt(r, current_workspace_fp="sha256:workspace2")


def test_altered_decision_rejected():
    r = make_receipt()
    r2 = dict(r)
    r2["decision"] = "allowed"   # same VALUE but body changed -> fingerprint mismatch
    r2["mutation_revision"] = 99
    with pytest.raises(ContractError):
        verify_receipt(r2, current_workspace_fp="sha256:workspace1")


def test_removed_receipt_id_rejected():
    r = make_receipt()
    r2 = {k: v for k, v in r.items() if k != "receipt_id"}
    with pytest.raises((ContractError, KeyError)):
        verify_receipt(r2, current_workspace_fp="sha256:workspace1")


def test_receipt_id_is_fingerprint():
    r = make_receipt()
    from harness.contracts.core import fingerprint as fp
    body = {k: v for k, v in r.items() if k != "receipt_id"}
    assert fp(body, "receipt/v1") == r["receipt_id"]


def test_blocked_decision_encoded():
    r = make_receipt(decision=GateDecision.BLOCKED)
    assert r["decision"] == "blocked"


def test_evidence_digest_binds_to_workspace():
    e = Evidence("ev1", "verification", 1, "sha256:ws1", {"x": 1}, now_ts())
    e2 = Evidence("ev1", "verification", 1, "sha256:ws2", {"x": 1}, now_ts())
    assert e.digest() != e2.digest()
