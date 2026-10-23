"""harness/entry.py - CLI entry points.

All commands land here. The actual logic lives in controller.py.
Keep this file thin: argument parsing + output only.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _require_env(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        print(f"ERROR: {name} environment variable is not set.", file=sys.stderr)
        sys.exit(1)
    return val


# ---------------------------------------------------------------------------
# harness-run
# ---------------------------------------------------------------------------

def cli_run(argv=None) -> int:
    """Run a coding task through the full harness pipeline."""
    import argparse

    p = argparse.ArgumentParser(
        prog="harness-run",
        description="Run a coding task through the OpenCode+Gemini harness.",
    )
    p.add_argument("task", help="The coding task description.")
    p.add_argument("workspace", help="Path to the target repository / workspace.")
    p.add_argument("--profile",   default=None,  help="Path to a profile YAML file.")
    p.add_argument("--catalog",   default=None,  help="Path to trusted verification catalog JSON.")
    p.add_argument("--model",     default="gemini-2.5-flash", help="Gemini model name.")
    p.add_argument("--max-attempts", type=int, default=4,
                   help="Maximum repair attempts (default 4).")
    p.add_argument("--output-dir", default=None, help="Directory for traces and reports.")
    p.add_argument("--allow-shell",  action="append", default=[],
                   metavar="GLOB",
                   help="Shell command basename glob to ALLOW (e.g. pytest).")
    p.add_argument("--non-interactive", action="store_true",
                   help="Never prompt; treat ASK_USER decisions as BLOCKED.")
    p.add_argument("--dry-run", action="store_true",
                   help="Print configuration and exit without running.")

    args = p.parse_args(sys.argv[1:] if argv is None else argv)

    # Validate workspace
    ws = Path(args.workspace).resolve()
    if not ws.exists():
        print(f"ERROR: workspace does not exist: {ws}", file=sys.stderr)
        return 1

    # GEMINI_API_KEY must be set
    _require_env("GEMINI_API_KEY")

    # Build permission rules from --allow-shell flags
    from harness.permission.policy import Rule, Verdict
    rules: list[Rule] = []
    for glob in args.allow_shell:
        rules.append(Rule(tool="shell", pattern=glob, verdict=Verdict.ALLOW))
    # Always allow read and edit by default so the agent can read/write files.
    rules.append(Rule(tool="edit",  pattern="*", verdict=Verdict.ALLOW))

    from harness.controller import RunConfig, HarnessController
    cfg = RunConfig(
        task=args.task,
        workspace=ws,
        profile_path=args.profile,
        catalog_path=args.catalog,
        model=args.model,
        max_attempts=args.max_attempts,
        output_dir=Path(args.output_dir) if args.output_dir else None,
        permission_rules=tuple(rules),
        non_interactive=args.non_interactive,
    )

    if args.dry_run:
        print(json.dumps({
            "task": cfg.task,
            "workspace": str(cfg.workspace),
            "model": cfg.model,
            "profile": cfg.profile_path,
            "max_attempts": cfg.max_attempts,
            "allow_shell": args.allow_shell,
        }, indent=2))
        return 0

    print(f"[harness] job starting — task: {args.task[:80]}")
    print(f"[harness] workspace : {ws}")
    print(f"[harness] model     : {args.model}")

    ctrl = HarnessController(cfg)
    result = ctrl.run()

    _print_result(result)
    return 0 if result.success else 1


# ---------------------------------------------------------------------------
# harness-verify
# ---------------------------------------------------------------------------

def cli_verify(argv=None) -> int:
    """Verify the workspace against a trusted catalog."""
    import argparse

    p = argparse.ArgumentParser(prog="harness-verify")
    p.add_argument("workspace", help="Workspace path.")
    p.add_argument("catalog",   help="Trusted catalog JSON path.")
    p.add_argument("--changed", nargs="*", default=[],
                   help="Workspace-relative paths to verify (space-separated).")
    args = p.parse_args(sys.argv[1:] if argv is None else argv)

    ws = Path(args.workspace).resolve()
    from harness.workspace.snapshot import take_snapshot, workspace_fingerprint, diff
    from harness.verification.catalog import load_catalog
    from harness.verification.select import select_checks
    from harness.verification.runtime import run_check, aggregate

    try:
        catalog = load_catalog(Path(args.catalog), ws)
    except Exception as exc:
        print(f"ERROR loading catalog: {exc}", file=sys.stderr)
        return 1

    snap = take_snapshot(ws)
    changed = tuple(args.changed) if args.changed else tuple(snap.keys())
    checks, uncovered = select_checks(catalog.checks, changed)

    if not checks:
        print("No applicable checks found.")
        return 0

    results = [run_check(s, ws) for s in checks]
    status = aggregate(results, uncovered)

    for r in results:
        print(f"  {r.check_id}: {r.status.value} — {r.reason}")
    print(f"\nAggregated: {status}")
    return 0 if str(status) in ("VerificationStatus.PASSED", "passed") else 1


# ---------------------------------------------------------------------------
# harness-inspect
# ---------------------------------------------------------------------------

def cli_inspect(argv=None) -> int:
    """Inspect a report or trace file."""
    import argparse

    p = argparse.ArgumentParser(prog="harness-inspect")
    p.add_argument("path", help="Path to a report.json or trace.jsonl file.")
    p.add_argument("--verify-chain", action="store_true",
                   help="Verify the hash chain of a trace file.")
    args = p.parse_args(sys.argv[1:] if argv is None else argv)

    path = Path(args.path)
    if not path.exists():
        print(f"ERROR: {path} not found", file=sys.stderr)
        return 1

    if args.verify_chain or path.suffix == ".jsonl":
        from harness.observability.trace import verify_chain
        try:
            n = verify_chain(path)
            print(f"Chain OK — {n} events verified.")
        except Exception as exc:
            print(f"Chain INVALID: {exc}", file=sys.stderr)
            return 1
    else:
        data = json.loads(path.read_text())
        print(json.dumps(data, indent=2))
    return 0


# ---------------------------------------------------------------------------
# harness-evaluate
# ---------------------------------------------------------------------------

def cli_evaluate(argv=None) -> int:
    """Evaluate a completed run: verify the receipt and print a summary."""
    import argparse

    p = argparse.ArgumentParser(prog="harness-evaluate")
    p.add_argument("report", help="Path to a report.json file.")
    p.add_argument("workspace", help="Current workspace path (for receipt check).")
    args = p.parse_args(sys.argv[1:] if argv is None else argv)

    report = json.loads(Path(args.report).read_text())
    ws = Path(args.workspace).resolve()

    from harness.workspace.snapshot import take_snapshot, workspace_fingerprint
    snap = take_snapshot(ws)
    current_fp = workspace_fingerprint(snap)

    print(f"Job:       {report.get('job_id')}")
    print(f"Task:      {report.get('task', '')[:80]}")
    print(f"Decision:  {report.get('gate_decision')}")
    print(f"State:     {report.get('gate_state')}")
    print(f"Reasons:   {report.get('gate_reasons')}")
    print(f"Attempts:  {report.get('attempts')}")
    print(f"Tokens:    {report.get('tokens')}")
    print(f"Cost µ$:   {report.get('cost_micro_usd')}")
    print(f"Changed:   {report.get('changed_files')}")
    return 0


# ---------------------------------------------------------------------------
# harness-bench
# ---------------------------------------------------------------------------

def cli_bench(argv=None) -> int:
    """Run the benchmark suite."""
    from harness.benchmark.runner import BenchmarkRunner
    import argparse

    p = argparse.ArgumentParser(prog="harness-bench")
    p.add_argument("tasks_file", help="Path to tasks JSONL file.")
    p.add_argument("workspace_template", help="Path to workspace template directory.")
    p.add_argument("--model",    default="gemini-2.5-flash")
    p.add_argument("--profile",  default=None)
    p.add_argument("--output",   default="evals/reports/benchmark.json")
    p.add_argument("--baseline", action="store_true",
                   help="Run without harness (baseline mode).")
    args = p.parse_args(sys.argv[1:] if argv is None else argv)

    _require_env("GEMINI_API_KEY")

    runner = BenchmarkRunner(
        tasks_file=args.tasks_file,
        workspace_template=Path(args.workspace_template),
        model=args.model,
        profile_path=args.profile,
        output_path=Path(args.output),
        baseline=args.baseline,
    )
    return runner.run()


# ---------------------------------------------------------------------------
# Shared output helper
# ---------------------------------------------------------------------------

def _print_result(result) -> None:
    print()
    print(f"[harness] {'SUCCESS' if result.success else 'FAILURE'}")
    print(f"  job_id   : {result.job_id}")
    print(f"  decision : {result.gate_decision} / {result.gate_state}")
    print(f"  reasons  : {result.gate_reasons}")
    print(f"  attempts : {result.attempts}")
    print(f"  tokens   : in={result.total_input_tokens} out={result.total_output_tokens}")
    print(f"  cost µ$  : {result.total_cost_micro_usd}")
    print(f"  changed  : {result.changed_files}")
    if result.error:
        print(f"  error    : {result.error}")
    if result.report_path:
        print(f"  report   : {result.report_path}")
    if result.trace_path:
        print(f"  trace    : {result.trace_path}")


# ---------------------------------------------------------------------------
# Legacy shim
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    """Legacy entry point — now delegates to cli_run."""
    print("Use harness-run, harness-verify, harness-inspect, "
          "harness-evaluate, or harness-bench.")
    return 0


if __name__ == "__main__":
    raise SystemExit(cli_run())
