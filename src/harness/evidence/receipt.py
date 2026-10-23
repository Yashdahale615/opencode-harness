"""harness/evidence/receipt.py - evidence, receipt and its verification."""
from __future__ import annotations

from dataclasses import asdict, dataclass

from harness.contracts.core import (ContractError, GateDecision, fingerprint,
                                    now_ts, safe_id)


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    kind: str                   # permission | verification | evaluation
    mutation_revision: int
    workspace_fp: str           # state this evidence is ABOUT
    payload: dict
    produced_at: str

    def digest(self) -> str:
        return fingerprint(asdict(self), "evidence/v1")


def build_receipt(*, job_id: str, session_id: str, decision: GateDecision,
                  evidence: list[Evidence], catalog_fp: str, command_fps,
                  workspace_fp: str, policy_fp: str,
                  mutation_revision: int) -> dict:
    body = {
        "schema_version": 1,
        "job_id": safe_id(job_id, "job_id"),
        "session_id": safe_id(session_id, "session_id"),
        "decision": decision.value,
        "evidence": sorted(e.digest() for e in evidence),
        "catalog_fp": catalog_fp,
        "command_fps": sorted(command_fps),
        "workspace_fp": workspace_fp,
        "policy_fp": policy_fp,
        "mutation_revision": mutation_revision,
        "issued_at": now_ts(),
    }
    return {**body, "receipt_id": fingerprint(body, "receipt/v1")}


def verify_receipt(receipt: dict, *, current_workspace_fp: str) -> None:
    body = {k: v for k, v in receipt.items() if k != "receipt_id"}
    if fingerprint(body, "receipt/v1") != receipt.get("receipt_id"):
        raise ContractError("receipt was altered")
    if receipt["workspace_fp"] != current_workspace_fp:
        raise ContractError("receipt does not describe the current workspace")
