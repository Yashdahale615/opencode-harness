#!/usr/bin/env python3
"""scripts/demo.py - clean interactive demo of the harness.

Run:
    python scripts/demo.py

Shows exactly what the harness does step by step.
"""
import os, sys, tempfile, warnings
warnings.filterwarnings("ignore")   # suppress FutureWarning noise

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pathlib import Path
from harness.permission.policy import Rule, Verdict
from harness.controller import RunConfig, HarnessController

def separator(title=""):
    print("\n" + "="*60)
    if title:
        print(f"  {title}")
        print("="*60)

def main():
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        print("ERROR: set GEMINI_API_KEY first")
        return 1

    # ── Fresh workspace ────────────────────────────────────────
    ws = Path(tempfile.mkdtemp(prefix="harness-demo-"))
    separator("HARNESS DEMO")
    print(f"  Workspace  : {ws}")
    print(f"  Model      : gemini-2.5-flash")
    print(f"  Task       : Create hello.py that prints Hello World")

    # ── Permission rules ───────────────────────────────────────
    # We allow file edits and python execution, deny everything else
    rules = (
        Rule("edit",  "*",       Verdict.ALLOW),   # allow all file writes
        Rule("shell", "python",  Verdict.ALLOW),   # allow: python
        Rule("shell", "python3", Verdict.ALLOW),   # allow: python3
        # everything else → DENY  (default-deny)
    )

    separator("STEP 1 — Running Gemini + Harness")
    print("  Sending task to Gemini...")
    print("  Every action will be permission-checked before execution.")
    print()

    cfg = RunConfig(
        task="Create a Python file named hello.py that prints 'Hello, World!' when executed.",
        workspace=ws,
        model="gemini-2.5-flash",
        max_attempts=3,
        permission_rules=rules,
        non_interactive=True,
    )

    ctrl = HarnessController(cfg)
    result = ctrl.run()

    # ── Results ────────────────────────────────────────────────
    separator("STEP 2 — Gate Decision")
    print(f"  Decision : {result.gate_decision.upper()}")
    print(f"  State    : {result.gate_state}")
    print(f"  Reasons  : {result.gate_reasons}")
    print()
    if result.gate_decision == "ask_user":
        print("  ℹ️  Gate says ASK_USER because there is no verification catalog.")
        print("     This means: Gemini DID write the file, but the harness cannot")
        print("     auto-approve without an independent test to confirm it works.")
        print("     In interactive mode it would ask YOU to approve.")

    separator("STEP 3 — What Gemini Created")
    created = [f for f in ws.rglob("*") if f.is_file() and ".harness" not in str(f)]
    if created:
        for f in created:
            print(f"  File: {f.name}")
            print(f"  Content:")
            print("  " + "-"*40)
            for line in f.read_text().splitlines():
                print(f"    {line}")
            print()
    else:
        print("  No files created.")

    separator("STEP 4 — Token Usage & Cost")
    print(f"  Input tokens  : {result.total_input_tokens}")
    print(f"  Output tokens : {result.total_output_tokens}")
    print(f"  Cost (micro$) : {result.total_cost_micro_usd}  (~${result.total_cost_micro_usd/1_000_000:.6f})")
    print(f"  Attempts      : {result.attempts}")

    separator("STEP 5 — Evidence Trail")
    print(f"  Trace log  : {result.trace_path}")
    print(f"  Report     : {result.report_path}")
    print()
    print("  The trace is hash-chained. If anyone tampers with it,")
    print("  harness-inspect --verify-chain will detect it.")

    separator("OVERALL")
    if result.changed_files:
        print(f"  ✅ Gemini successfully created: {result.changed_files}")
        print(f"  🛡️  Harness tracked every action with a tamper-proof receipt.")
    else:
        print(f"  ❌ No files were created. Error: {result.error}")

    print()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
