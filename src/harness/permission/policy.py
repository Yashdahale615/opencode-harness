"""harness/permission/policy.py - risk classification + rule evaluation."""
from __future__ import annotations

import os
from dataclasses import dataclass
from fnmatch import fnmatchcase

from harness.contracts.core import Verdict


@dataclass(frozen=True)
class ToolRequest:
    tool: str                    # "shell" | "edit" | "mcp:<server>.<tool>"
    argv: tuple[str, ...] = ()   # for shell
    path: str = ""               # for edit (workspace-relative)


@dataclass(frozen=True)
class Rule:
    tool: str                    # glob on ToolRequest.tool
    pattern: str                 # glob on argv[0] basename or path
    verdict: Verdict


_HIGH = {"sudo", "su", "rm", "dd", "mkfs", "chmod", "chown", "curl", "wget",
         "ssh", "scp", "nc", "kill", "pkill"}


def classify_risk(req: ToolRequest) -> str:
    if req.tool == "shell" and req.argv:
        base = os.path.basename(req.argv[0])
        if base in _HIGH:
            return "high"
        if base == "git" and any(a in req.argv for a in ("push", "reset")):
            return "high"
        return "medium"
    if req.tool == "edit":
        p = req.path
        if p.startswith(".git") or p.startswith(".harness"):
            return "high"
        return "low"
    return "high" if req.tool.startswith("mcp:") else "medium"


def evaluate(rules: tuple[Rule, ...], req: ToolRequest) -> Verdict:
    """First match wins. No match -> DENY (default deny)."""
    target = os.path.basename(req.argv[0]) if req.argv else req.path
    for r in rules:
        if fnmatchcase(req.tool, r.tool) and fnmatchcase(target, r.pattern):
            return r.verdict
    return Verdict.DENY
