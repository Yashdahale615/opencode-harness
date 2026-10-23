#!/usr/bin/env python3
"""scripts/smoke_test.py - quick end-to-end smoke test.

Usage:
    python scripts/smoke_test.py

Requires GEMINI_API_KEY to be set.
"""
import os
import sys
import tempfile
import json
from pathlib import Path

# Ensure harness is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from harness.permission.policy import Rule, Verdict
from harness.controller import RunConfig, HarnessController


def main():
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        print("ERROR: GEMINI_API_KEY not set", file=sys.stderr)
        return 1

    # Create a fresh workspace
    tmp = Path(tempfile.mkdtemp(prefix="harness-smoke-"))
    print(f"Workspace: {tmp}")

    rules = (
        Rule("edit",  "*",      Verdict.ALLOW),
        Rule("shell", "python", Verdict.ALLOW),
        Rule("shell", "python3", Verdict.ALLOW),
    )

    cfg = RunConfig(
        task="Create a Python file named hello.py that prints 'Hello, World!' when run.",
        workspace=tmp,
        model="gemini-2.5-flash",
        max_attempts=3,
        permission_rules=rules,
        non_interactive=True,
    )

    ctrl = HarnessController(cfg)
    result = ctrl.run()

    print()
    print("=" * 60)
    print(f"Success:   {result.success}")
    print(f"Decision:  {result.gate_decision} / {result.gate_state}")
    print(f"Reasons:   {result.gate_reasons}")
    print(f"Attempts:  {result.attempts}")
    print(f"Tokens:    in={result.total_input_tokens} out={result.total_output_tokens}")
    print(f"Changed:   {result.changed_files}")
    print(f"Trace:     {result.trace_path}")
    print(f"Report:    {result.report_path}")
    if result.error:
        print(f"Error:     {result.error}")

    # Show created files
    created = list(tmp.rglob("*.py"))
    if created:
        print()
        print("Files created:")
        for f in created:
            if ".harness" not in str(f):
                print(f"  {f.relative_to(tmp)}")
                print("  ---")
                print("  " + f.read_text()[:300])

    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
