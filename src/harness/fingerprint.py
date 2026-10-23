"""harness/fingerprint.py - convenience re-export of the fingerprinting
primitives defined in harness.contracts.core (canonical JSON + SHA-256,
domain-separated). Kept as a top-level module because fingerprinting is
referenced from almost every other part of the harness (receipts, traces,
snapshots, catalogs) and a short import path avoids repeating the deeper
`harness.contracts.core` path everywhere.
"""
from __future__ import annotations

from harness.contracts.core import canonical_json, fingerprint, now_ts, safe_id

__all__ = ["canonical_json", "fingerprint", "now_ts", "safe_id"]
