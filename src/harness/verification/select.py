"""harness/verification/select.py - scope and cost based check selection."""
from __future__ import annotations

from fnmatch import fnmatchcase

from harness.verification.catalog import CheckSpec


def covers(check: CheckSpec, path: str) -> bool:
    # fnmatch '*' also matches '/', so "tests/*" covers tests/unit/a.py.
    return any(fnmatchcase(path, g) for g in check.scope)


def select_checks(checks, changed: tuple[str, ...]):
    """Return (ordered checks to run, changed paths nobody covers)."""
    applicable = sorted((c for c in checks
                         if any(covers(c, p) for p in changed)),
                        key=lambda c: (c.cost_rank, c.check_id))
    uncovered = tuple(p for p in changed
                      if not any(covers(c, p) for c in applicable))
    return applicable, uncovered
