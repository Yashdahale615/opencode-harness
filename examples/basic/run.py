#!/usr/bin/env python3
"""Minimal example: evaluate one tool request against a permission policy."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from harness.permission.policy import Rule, ToolRequest, classify_risk, evaluate
from harness.contracts.core import Verdict

rules = (Rule(tool="edit", pattern="*.py", verdict=Verdict.ALLOW),)
req = ToolRequest(tool="edit", path="src/app.py")
print("risk:", classify_risk(req))
print("verdict:", evaluate(rules, req))
