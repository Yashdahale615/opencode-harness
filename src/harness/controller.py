"""harness/controller.py - end-to-end run loop.

Wires together: LLM → permission gate → execution → verification → gate
decision → evidence → trace.

The controller is the only place where side-effects (filesystem mutations,
subprocess calls, LLM round-trips) are orchestrated. All of the constituent
modules it delegates to are stateless and independently testable.
"""
from __future__ import annotations

import json
import os
import pathlib
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

from harness.contracts.core import (
    GateDecision,
    VerificationStatus,
    fingerprint,
    now_ts,
    safe_id,
)
from harness.evidence.receipt import Evidence, build_receipt
from harness.gate.decision import (
    AcceptancePolicy,
    GateInput,
    GateOutcome,
    decide,
)
from harness.gate.reconcile import reconcile
from harness.llm.gemini import GeminiClient, ModelTurn, ToolAction
from harness.observability.trace import TraceWriter
from harness.orchestration.state import Budget, BudgetExceeded, RunMachine, RunState
from harness.permission.policy import Rule, ToolRequest, Verdict, classify_risk, evaluate
from harness.verification.catalog import CheckSpec, load_catalog
from harness.verification.runtime import VerificationResult, aggregate, run_check
from harness.verification.select import select_checks
from harness.workspace.snapshot import diff, take_snapshot, workspace_fingerprint


# ---------------------------------------------------------------------------
# Profile loader
# ---------------------------------------------------------------------------

def _load_profile(path: str | None) -> dict:
    """Load YAML profile or return a default."""
    if path and os.path.exists(path):
        with open(path) as fh:
            return yaml.safe_load(fh) or {}
    return {
        "name": "default",
        "acceptance_policy": {
            "allow_unverified_low_risk": False,
            "max_reverify": 2,
        },
        "permission": {"default_verdict": "deny"},
    }


def _make_policy(profile: dict) -> AcceptancePolicy:
    ap = profile.get("acceptance_policy", {})
    return AcceptancePolicy(
        allow_unverified_low_risk=bool(ap.get("allow_unverified_low_risk", False)),
        max_reverify=int(ap.get("max_reverify", 2)),
    )


# ---------------------------------------------------------------------------
# Run configuration
# ---------------------------------------------------------------------------

@dataclass
class RunConfig:
    task: str
    workspace: Path
    profile_path: str | None = None
    catalog_path: str | None = None   # path to trusted check catalog JSON
    model: str = "gemini-2.5-flash"
    max_attempts: int = 4
    max_tokens: int = 400_000
    max_cost_micro_usd: int = 5_000_000   # $5
    output_dir: Path | None = None
    permission_rules: tuple[Rule, ...] = field(default_factory=tuple)
    non_interactive: bool = False


# ---------------------------------------------------------------------------
# Run result
# ---------------------------------------------------------------------------

@dataclass
class RunResult:
    job_id: str
    task: str
    success: bool
    gate_decision: str
    gate_state: str
    gate_reasons: list[str]
    attempts: int
    total_input_tokens: int
    total_output_tokens: int
    total_cost_micro_usd: int
    duration_ms: int
    workspace_fp: str
    changed_files: list[str]
    verification_results: list[dict]
    receipt: dict | None
    trace_path: str
    report_path: str | None
    error: str | None


# ---------------------------------------------------------------------------
# Controller
# ---------------------------------------------------------------------------

class HarnessController:
    """One instance per run. Not thread-safe."""

    def __init__(self, cfg: RunConfig) -> None:
        self.cfg = cfg
        self.job_id = _make_job_id()
        self.profile = _load_profile(cfg.profile_path)
        self.policy = _make_policy(self.profile)
        self.machine = RunMachine()
        self.budget = Budget(
            max_tokens=cfg.max_tokens,
            max_cost_micro_usd=cfg.max_cost_micro_usd,
            max_attempts=cfg.max_attempts,
        )
        self.output_dir = cfg.output_dir or (cfg.workspace / ".harness" / self.job_id)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        trace_path = self.output_dir / "trace.jsonl"
        self.trace = TraceWriter(trace_path, self.job_id)
        self._trace_path = trace_path
        self.llm = GeminiClient(model_name=cfg.model)
        self._history: list[dict] = []
        self._evidence: list[Evidence] = []
        self._permission_violations = 0
        self._all_ver_results: list[VerificationResult] = []

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self) -> RunResult:
        t0 = time.monotonic()
        error: str | None = None
        receipt: dict | None = None
        outcome: GateOutcome | None = None
        reverify_count = 0
        total_in = total_out = total_cost = 0
        changed_files: list[str] = []
        workspace_fp = ""

        try:
            self.machine.go(RunState.CONTEXT_READY)
            self.trace.emit("harness_start", {
                "job_id": self.job_id,
                "task": self.cfg.task,
                "workspace": str(self.cfg.workspace),
                "profile": self.profile.get("name", "default"),
                "model": self.cfg.model,
            })

            # --- Initial workspace snapshot ----------------------------
            snap_before = take_snapshot(self.cfg.workspace)
            workspace_fp = workspace_fingerprint(snap_before)
            self.trace.emit("snapshot", {"phase": "initial", "fp": workspace_fp})
            self.machine.go(RunState.PLANNED)

            # --- Main repair loop --------------------------------------
            run_succeeded = False
            snap_after = snap_before

            while True:
                self.budget.start_attempt()
                self.machine.go(RunState.EXECUTING)

                # Build user message (first turn vs. repair)
                if self.budget.attempts == 1:
                    user_msg = _build_task_message(self.cfg.task, self.cfg.workspace)
                else:
                    diag = _build_diagnostics(self._all_ver_results)
                    user_msg = (
                        f"The previous attempt failed verification.\n\n"
                        f"Diagnostics:\n{diag}\n\n"
                        f"Please fix the issues and try again."
                    )

                self.trace.emit("llm_request", {
                    "attempt": self.budget.attempts,
                    "message_len": len(user_msg),
                })

                # --- LLM call -----------------------------------------
                turn = self.llm.send(user_msg, history=self._history)
                total_in  += turn.input_tokens
                total_out += turn.output_tokens
                # rough Gemini Flash pricing: $0.075/1M input, $0.30/1M output
                cost = (turn.input_tokens * 75 + turn.output_tokens * 300) // 1_000_000
                total_cost += cost
                self.budget.charge(
                    tokens=turn.input_tokens + turn.output_tokens,
                    cost_micro_usd=cost,
                )
                self._history.append({"role": "user", "content": user_msg})
                self._history.append({"role": "model", "content": turn.raw_text})

                self.trace.emit("llm_response", {
                    "attempt": self.budget.attempts,
                    "actions": len(turn.actions),
                    "explanation": turn.explanation,
                    "input_tokens": turn.input_tokens,
                    "output_tokens": turn.output_tokens,
                    "duration_ms": turn.duration_ms,
                })

                # --- Execute approved actions --------------------------
                snap_after, run_succeeded = self._execute_turn(
                    turn, snap_before if self.budget.attempts == 1 else snap_after
                )

                # --- Verification -------------------------------------
                self.machine.go(RunState.VERIFYING)
                snap_after_ver = take_snapshot(self.cfg.workspace)
                d = diff(snap_before, snap_after_ver)
                changed_files = list(d.changed)
                workspace_fp = workspace_fingerprint(snap_after_ver)

                ver_results, ver_status = self._run_verification(d.changed)
                self._all_ver_results.extend(ver_results)

                snap_post_ver = take_snapshot(self.cfg.workspace)
                recon = reconcile(snap_after_ver, snap_post_ver, self.budget.attempts)

                # --- Gate decision ------------------------------------
                self.machine.go(RunState.GATING)
                # Risk = low when only file edits happened (no shell commands)
                all_kinds = {a.kind for t2 in [turn] for a in t2.actions}
                risk = "low" if all_kinds <= {"edit", "read", "done"} else "medium"
                g_input = GateInput(
                    run_succeeded=run_succeeded,
                    workspace_changed=bool(d),
                    permission_violations=self._permission_violations,
                    risk=risk,
                    verification=ver_status,
                    reconciled_unchanged=recon.unchanged,
                    reverify_count=reverify_count,
                    policy=self.policy,
                )
                outcome = decide(g_input)
                self.trace.emit("gate_decision", {
                    "state": outcome.state.value,
                    "decision": outcome.decision.value,
                    "reasons": list(outcome.reasons),
                    "attempt": self.budget.attempts,
                })

                # --- Decide what to do with outcome -------------------
                if outcome.decision == GateDecision.ALLOWED:
                    self.machine.go(RunState.TERMINAL_VERIFIED)
                    break

                if outcome.decision == GateDecision.ASK_USER:
                    if self.profile.get("non_interactive") or self.cfg.non_interactive:
                        # Non-interactive mode: treat ASK_USER as failure
                        self.machine.go(RunState.TERMINAL_BLOCKED)
                        break
                    ans = _ask_user(outcome)
                    if ans:
                        self.machine.go(RunState.TERMINAL_VERIFIED)
                        break
                    else:
                        self.machine.go(RunState.TERMINAL_BLOCKED)
                        break

                # BLOCKED: check if we can retry
                if outcome.decision == GateDecision.BLOCKED:
                    # Can we reverify?
                    if (outcome.state.value == "reverify"
                            and reverify_count < self.policy.max_reverify):
                        reverify_count += 1
                        self.machine.go(RunState.VERIFYING)
                        continue
                    # Can we repair (verification failed / run failed)?
                    if (outcome.state.value in ("blocked", "run_failed")
                            and self.budget.attempts < self.cfg.max_attempts):
                        # Go back to EXECUTING for next attempt
                        # (state machine allows GATING -> EXECUTING)
                        continue
                    self.machine.go(RunState.TERMINAL_BLOCKED)
                    break

        except BudgetExceeded as exc:
            error = f"budget_exceeded: {exc}"
            self.trace.emit("budget_exceeded", {"reason": str(exc)})
            if self.machine.state not in (
                RunState.TERMINAL_VERIFIED,
                RunState.TERMINAL_BLOCKED,
                RunState.TERMINAL_FAILED,
            ):
                self.machine.go(RunState.TERMINAL_FAILED)

        except Exception as exc:  # noqa: BLE001
            error = f"unexpected_error: {type(exc).__name__}: {exc}"
            self.trace.emit("error", {"reason": error})
            if self.machine.state not in (
                RunState.TERMINAL_VERIFIED,
                RunState.TERMINAL_BLOCKED,
                RunState.TERMINAL_FAILED,
            ):
                self.machine.go(RunState.TERMINAL_FAILED)

        finally:
            self.trace.close()

        # --- Build evidence + receipt ---------------------------------
        final_state = self.machine.state
        success = final_state == RunState.TERMINAL_VERIFIED

        if outcome:
            receipt = self._build_evidence_receipt(
                outcome, workspace_fp, self.budget.attempts
            )
            report_path = self._write_report(
                outcome, receipt, changed_files, total_in, total_out, total_cost, error
            )
        else:
            report_path = None

        duration_ms = int((time.monotonic() - t0) * 1000)

        return RunResult(
            job_id=self.job_id,
            task=self.cfg.task,
            success=success,
            gate_decision=outcome.decision.value if outcome else "none",
            gate_state=outcome.state.value if outcome else "none",
            gate_reasons=list(outcome.reasons) if outcome else [],
            attempts=self.budget.attempts,
            total_input_tokens=total_in,
            total_output_tokens=total_out,
            total_cost_micro_usd=total_cost,
            duration_ms=duration_ms,
            workspace_fp=workspace_fp,
            changed_files=changed_files,
            verification_results=[_ver_to_dict(r) for r in self._all_ver_results],
            receipt=receipt,
            trace_path=str(self._trace_path),
            report_path=str(report_path) if report_path else None,
            error=error,
        )

    # ------------------------------------------------------------------
    # Action execution
    # ------------------------------------------------------------------

    def _execute_turn(
        self, turn: ModelTurn, snap_pre: dict
    ) -> tuple[dict, bool]:
        """Execute all approved actions from one LLM turn.
        Returns (new snapshot, run_succeeded)."""
        run_succeeded = True
        for action in turn.actions:
            if action.kind == "done":
                break
            ok = self._execute_action(action)
            if not ok:
                run_succeeded = False
        snap_post = take_snapshot(self.cfg.workspace)
        return snap_post, run_succeeded

    def _execute_action(self, action: ToolAction) -> bool:
        """Permission-check then execute one action. Returns True on success."""
        req = _action_to_request(action)
        verdict = evaluate(self.cfg.permission_rules, req)
        risk = classify_risk(req)

        self.trace.emit("permission_check", {
            "action_kind": action.kind,
            "verdict": verdict.value,
            "risk": risk,
            "description": action.description,
        })

        if verdict == Verdict.DENY:
            self._permission_violations += 1
            self.trace.emit("action_denied", {"kind": action.kind, "risk": risk})
            print(f"  [DENIED] {action.description or action.kind}")
            return False

        if verdict == Verdict.ASK:
            if self.cfg.non_interactive or self.profile.get("non_interactive"):
                self._permission_violations += 1
                self.trace.emit("action_denied", {"kind": action.kind, "reason": "non_interactive_ask"})
                return False
            ans = input(f"  [ASK] Allow {action.description or action.kind}? [y/N] ")
            if ans.strip().lower() != "y":
                self._permission_violations += 1
                return False

        # Execute
        return self._do_action(action)

    def _do_action(self, action: ToolAction) -> bool:
        """Actually perform the action. Returns True on success."""
        try:
            if action.kind == "edit":
                target = self.cfg.workspace / action.path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(action.content, encoding="utf-8")
                self.trace.emit("action_executed", {
                    "kind": "edit", "path": action.path, "bytes": len(action.content)
                })
                print(f"  [EDIT]  {action.path}")
                return True

            if action.kind == "read":
                target = self.cfg.workspace / action.path
                if target.exists():
                    content = target.read_text(encoding="utf-8", errors="replace")
                    # Feed back to LLM via history
                    self._history.append({
                        "role": "user",
                        "content": f"Contents of {action.path}:\n```\n{content}\n```",
                    })
                self.trace.emit("action_executed", {"kind": "read", "path": action.path})
                print(f"  [READ]  {action.path}")
                return True

            if action.kind == "shell":
                # Shell commands require absolute paths in argv[0]; if the
                # model gives a relative command, attempt to resolve via PATH.
                argv = action.argv
                if not argv:
                    return False
                if not os.path.isabs(argv[0]):
                    import shutil
                    resolved = shutil.which(argv[0])
                    if not resolved:
                        self.trace.emit("action_failed", {
                            "kind": "shell", "reason": f"not found: {argv[0]}"
                        })
                        print(f"  [SHELL FAIL] command not found: {argv[0]}")
                        return False
                    argv = [resolved] + argv[1:]

                import subprocess
                result = subprocess.run(
                    argv,
                    cwd=str(self.cfg.workspace),
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                self.trace.emit("action_executed", {
                    "kind": "shell",
                    "argv": argv,
                    "exit_code": result.returncode,
                    "stdout_tail": result.stdout[-2000:],
                    "stderr_tail": result.stderr[-2000:],
                })
                success = result.returncode == 0
                print(f"  [SHELL] exit={result.returncode}: {' '.join(argv[:3])}")
                if not success and result.stderr:
                    print(f"    stderr: {result.stderr[:400]}")
                return success

            # Unknown kind
            self.trace.emit("action_skipped", {"kind": action.kind})
            return True

        except Exception as exc:  # noqa: BLE001
            self.trace.emit("action_error", {"kind": action.kind, "error": str(exc)})
            print(f"  [ERROR] {action.kind}: {exc}")
            return False

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    def _run_verification(
        self, changed: tuple[str, ...]
    ) -> tuple[list[VerificationResult], VerificationStatus | None]:
        if not self.cfg.catalog_path or not os.path.exists(self.cfg.catalog_path):
            self.trace.emit("verification_skipped", {"reason": "no_catalog"})
            return [], None

        try:
            import harness.verification.catalog as _cat_mod
            catalog = _cat_mod.load_catalog(
                Path(self.cfg.catalog_path), self.cfg.workspace
            )
        except Exception as exc:
            self.trace.emit("catalog_load_failed", {"error": str(exc)})
            return [], None

        checks, uncovered = select_checks(catalog.checks, changed)
        results: list[VerificationResult] = []
        for spec in checks:
            r = run_check(spec, self.cfg.workspace)
            results.append(r)
            self.trace.emit("check_result", {
                "check_id": r.check_id,
                "status": r.status.value,
                "reason": r.reason,
                "exit_code": r.exit_code,
                "duration_ms": r.duration_ms,
            })
            print(f"  [VERIFY] {r.check_id}: {r.status.value}")

        status = aggregate(results, uncovered)
        return results, status

    # ------------------------------------------------------------------
    # Evidence + report
    # ------------------------------------------------------------------

    def _build_evidence_receipt(
        self, outcome: GateOutcome, workspace_fp: str, mutation_revision: int
    ) -> dict:
        ev = Evidence(
            evidence_id=f"ev-{self.job_id}",
            kind="verification",
            mutation_revision=mutation_revision,
            workspace_fp=workspace_fp,
            payload={
                "gate_state": outcome.state.value,
                "gate_decision": outcome.decision.value,
                "reasons": list(outcome.reasons),
            },
            produced_at=now_ts(),
        )
        self._evidence.append(ev)

        return build_receipt(
            job_id=self.job_id,
            session_id=f"s-{self.job_id}",
            decision=outcome.decision,
            evidence=self._evidence,
            catalog_fp=fingerprint({"catalog": self.cfg.catalog_path or ""}, "catalog/v1"),
            command_fps=[],
            workspace_fp=workspace_fp,
            policy_fp=fingerprint(self.profile, "policy/v1"),
            mutation_revision=mutation_revision,
        )

    def _write_report(
        self,
        outcome: GateOutcome,
        receipt: dict,
        changed_files: list[str],
        total_in: int,
        total_out: int,
        total_cost: int,
        error: str | None,
    ) -> Path:
        report = {
            "schema_version": 1,
            "job_id": self.job_id,
            "task": self.cfg.task,
            "profile": self.profile.get("name"),
            "model": self.cfg.model,
            "gate_decision": outcome.decision.value,
            "gate_state": outcome.state.value,
            "gate_reasons": list(outcome.reasons),
            "attempts": self.budget.attempts,
            "tokens": {"input": total_in, "output": total_out},
            "cost_micro_usd": total_cost,
            "changed_files": changed_files,
            "verification_results": [_ver_to_dict(r) for r in self._all_ver_results],
            "receipt_id": receipt.get("receipt_id"),
            "error": error,
            "generated_at": now_ts(),
        }
        path = self.output_dir / "report.json"
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_job_id() -> str:
    """Generate a safe job ID."""
    raw = uuid.uuid4().hex[:12]
    return f"job-{raw}"


def _build_task_message(task: str, workspace: Path) -> str:
    """Compose the first user message."""
    lines = [
        f"Task: {task}",
        f"",
        f"Workspace root: {workspace}",
        f"",
        "Analyse the task, read any relevant files first (kind=read), then make "
        "the necessary edits (kind=edit) or run commands (kind=shell). "
        "When done, emit a single action with kind=done.",
    ]
    # Attach top-level file listing for context
    try:
        entries = sorted(
            p.relative_to(workspace).as_posix()
            for p in workspace.rglob("*")
            if p.is_file()
            and not any(
                part in (".git", ".harness", "__pycache__", "node_modules")
                for part in p.parts
            )
        )[:60]
        if entries:
            lines += ["", "Files in workspace:", *entries]
    except Exception:  # noqa: BLE001
        pass
    return "\n".join(lines)


def _build_diagnostics(results: list[VerificationResult]) -> str:
    if not results:
        return "No verification results available."
    lines: list[str] = []
    for r in results:
        lines.append(f"- {r.check_id}: {r.status.value} ({r.reason})")
        if r.stderr_tail:
            lines.append(f"  stderr: {r.stderr_tail[:500]}")
        if r.stdout_tail:
            lines.append(f"  stdout: {r.stdout_tail[:500]}")
    return "\n".join(lines)


def _action_to_request(action: ToolAction) -> ToolRequest:
    """Convert a ToolAction to the ToolRequest the permission layer understands."""
    if action.kind == "shell":
        return ToolRequest(tool="shell", argv=tuple(action.argv))
    if action.kind in ("edit", "read"):
        return ToolRequest(tool="edit", path=action.path)
    return ToolRequest(tool=f"agent:{action.kind}")


def _ver_to_dict(r: VerificationResult) -> dict:
    return {
        "check_id": r.check_id,
        "status": r.status.value,
        "reason": r.reason,
        "exit_code": r.exit_code,
        "duration_ms": r.duration_ms,
        "stdout_tail": r.stdout_tail,
        "stderr_tail": r.stderr_tail,
    }


def _ask_user(outcome: GateOutcome) -> bool:
    """Prompt the user for approval.  Returns True if approved."""
    print(f"\n[GATE] ASK_USER: {outcome.state.value} — {', '.join(outcome.reasons)}")
    ans = input("Accept the result? [y/N] ").strip().lower()
    return ans == "y"
