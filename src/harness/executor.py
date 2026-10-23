"""harness/executor.py - convenience re-export of contained subprocess
execution, implemented in harness.execution.process.
"""
from __future__ import annotations

from harness.execution.process import *  # noqa: F401,F403
from harness.execution import process as _process

__all__ = [n for n in dir(_process) if not n.startswith("_")]
