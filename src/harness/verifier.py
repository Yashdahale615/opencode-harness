"""harness/verifier.py - convenience re-export of the verification layer:
trusted-check catalog loading (harness.verification.catalog), scope/cost
based check selection (harness.verification.select), and check execution +
aggregation (harness.verification.runtime).
"""
from __future__ import annotations

from harness.verification.catalog import CheckSpec, load_catalog, validate_check
from harness.verification.select import covers, select_checks
from harness.verification.runtime import aggregate, run_check

__all__ = [
    "CheckSpec", "load_catalog", "validate_check",
    "covers", "select_checks",
    "aggregate", "run_check",
]
