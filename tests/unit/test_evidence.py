"""Unit tests for harness.evidence.receipt."""
import pytest
from harness.contracts.core import ContractError, GateDecision, now_ts
from harness.evidence.receipt import Evidence, build_receipt, verify_receipt


def make_receipt(ws_fp="sha256:aa"):
    e = Evidence(
        evidence_id="ev-1",
        kind="verification",
        mutation_revision=1,
        workspace_fp=ws_fp,
        payload={"status": "passed"},
        produced_at=now_ts(),
    )
    return build_receipt(
        job_id="job-1",
        session_id="s-1",
        decision=GateDecision.ALLOWED,
        evidence=[e],
        catalog_fp="sha256:cc",
        command_fps=["sha256:dd"],
        workspace_fp=ws_fp,
        policy_fp="sha256:pp",
        mutation_revision=1,
    ), e


def test_receipt_valid():
    r, _ = make_receipt()
    verify_receipt(r, current_workspace_fp="sha256:aa")  # no exception


def test_receipt_workspace_mismatch():
    r, _ = make_receipt()
    with pytest.raises(ContractError, match="current workspace"):
        verify_receipt(r, current_workspace_fp="sha256:bb")


def test_receipt_body_altered():
    r, _ = make_receipt()
    r2 = dict(r)
    r2["decision"] = "blocked"   # alter a field
    with pytest.raises(ContractError, match="altered"):
        verify_receipt(r2, current_workspace_fp="sha256:aa")


def test_evidence_digest_stable():
    e = Evidence("ev-1", "verification", 1, "sha256:aa", {"x": 1}, now_ts())
    assert e.digest() == e.digest()


def test_evidence_digest_changes():
    e1 = Evidence("ev-1", "verification", 1, "sha256:aa", {"x": 1}, now_ts())
    e2 = Evidence("ev-1", "verification", 1, "sha256:aa", {"x": 2}, now_ts())
    assert e1.digest() != e2.digest()


def test_receipt_has_receipt_id():
    r, _ = make_receipt()
    assert "receipt_id" in r
    assert r["receipt_id"].startswith("sha256:")
