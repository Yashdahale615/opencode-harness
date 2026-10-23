"""harness/benchmark/runner.py - reproducible benchmark harness.

Runs each task in tasks_file against a fresh copy of workspace_template,
once with the full harness and once in baseline mode (no permission gate,
no verification, just raw LLM output written to disk).  Results are saved
as machine-readable JSON.

Metrics collected per task:
  - success          : bool
  - gate_decision    : str
  - attempts         : int
  - input_tokens     : int
  - output_tokens    : int
  - cost_micro_usd   : int
  - duration_ms      : int
  - changed_files    : list[str]
  - verification_results : list[dict]
"""
from __future__ import annotations

import copy
import json
import os
import pathlib
import shutil
import tempfile
import time
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


@dataclass
class TaskSpec:
    task_id: str
    description: str
    expected_files: list[str] = None      # optional: files that should exist after
    expected_exit_zero: bool = True


@dataclass
class TaskResult:
    task_id: str
    mode: str                # "harness" | "baseline"
    success: bool
    gate_decision: str
    gate_state: str
    attempts: int
    input_tokens: int
    output_tokens: int
    cost_micro_usd: int
    duration_ms: int
    changed_files: list[str]
    error: str | None


class BenchmarkRunner:
    def __init__(
        self,
        tasks_file: str | Path,
        workspace_template: Path,
        *,
        model: str = "gemini-2.5-flash",
        profile_path: str | None = None,
        output_path: Path = Path("evals/reports/benchmark.json"),
        baseline: bool = False,
    ) -> None:
        self.tasks_file = Path(tasks_file)
        self.workspace_template = workspace_template
        self.model = model
        self.profile_path = profile_path
        self.output_path = Path(output_path)
        self.baseline = baseline

    # ------------------------------------------------------------------

    def run(self) -> int:
        tasks = self._load_tasks()
        if not tasks:
            print("No tasks found. Create a tasks JSONL file first.")
            return 1

        print(f"[bench] Running {len(tasks)} tasks, model={self.model}, "
              f"mode={'baseline' if self.baseline else 'harness'}")

        results: list[TaskResult] = []
        for i, task in enumerate(tasks, 1):
            print(f"\n[bench] Task {i}/{len(tasks)}: {task.task_id}")
            result = self._run_task(task)
            results.append(result)
            _print_task_result(result)

        summary = _summarise(results)
        self._save(results, summary)
        print(f"\n[bench] Done. Results: {self.output_path}")
        _print_summary(summary)
        return 0

    # ------------------------------------------------------------------

    def _load_tasks(self) -> list[TaskSpec]:
        tasks = []
        with open(self.tasks_file) as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                obj = json.loads(line)
                tasks.append(TaskSpec(
                    task_id=obj["task_id"],
                    description=obj["description"],
                    expected_files=obj.get("expected_files"),
                    expected_exit_zero=obj.get("expected_exit_zero", True),
                ))
        return tasks

    # ------------------------------------------------------------------

    def _run_task(self, task: TaskSpec) -> TaskResult:
        # Clone workspace template into a temp dir
        tmp = Path(tempfile.mkdtemp(prefix=f"bench-{task.task_id}-"))
        try:
            if self.workspace_template.exists():
                shutil.copytree(str(self.workspace_template), str(tmp / "ws"))
            else:
                (tmp / "ws").mkdir()
            ws = tmp / "ws"

            t0 = time.monotonic()
            if self.baseline:
                result = self._run_baseline(task, ws)
            else:
                result = self._run_harness(task, ws)
            result.duration_ms = int((time.monotonic() - t0) * 1000)
            return result
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    # ------------------------------------------------------------------

    def _run_harness(self, task: TaskSpec, ws: Path) -> TaskResult:
        from harness.permission.policy import Rule, Verdict
        from harness.controller import RunConfig, HarnessController

        # Permissive rules for benchmark (allow common dev commands)
        rules = (
            Rule(tool="shell", pattern="pytest",   verdict=Verdict.ALLOW),
            Rule(tool="shell", pattern="python",   verdict=Verdict.ALLOW),
            Rule(tool="shell", pattern="python3",  verdict=Verdict.ALLOW),
            Rule(tool="shell", pattern="pip",      verdict=Verdict.ALLOW),
            Rule(tool="shell", pattern="git",      verdict=Verdict.ALLOW),
            Rule(tool="shell", pattern="npm",      verdict=Verdict.ALLOW),
            Rule(tool="shell", pattern="node",     verdict=Verdict.ALLOW),
            Rule(tool="edit",  pattern="*",        verdict=Verdict.ALLOW),
        )
        cfg = RunConfig(
            task=task.description,
            workspace=ws,
            profile_path=self.profile_path,
            model=self.model,
            max_attempts=3,
            output_dir=ws / ".harness",
            permission_rules=rules,
            non_interactive=True,
        )
        try:
            ctrl = HarnessController(cfg)
            r = ctrl.run()
            return TaskResult(
                task_id=task.task_id,
                mode="harness",
                success=r.success,
                gate_decision=r.gate_decision,
                gate_state=r.gate_state,
                attempts=r.attempts,
                input_tokens=r.total_input_tokens,
                output_tokens=r.total_output_tokens,
                cost_micro_usd=r.total_cost_micro_usd,
                duration_ms=0,
                changed_files=r.changed_files,
                error=r.error,
            )
        except Exception as exc:  # noqa: BLE001
            return TaskResult(
                task_id=task.task_id,
                mode="harness",
                success=False,
                gate_decision="error",
                gate_state="error",
                attempts=0,
                input_tokens=0,
                output_tokens=0,
                cost_micro_usd=0,
                duration_ms=0,
                changed_files=[],
                error=str(exc),
            )

    # ------------------------------------------------------------------

    def _run_baseline(self, task: TaskSpec, ws: Path) -> TaskResult:
        """Baseline: call Gemini directly, write output, no gate."""
        from harness.llm.gemini import GeminiClient

        client = GeminiClient(model_name=self.model)

        try:
            # Single-shot: ask the model to produce the code
            msg = (
                f"Task: {task.description}\n\n"
                f"Workspace root: {ws}\n\n"
                "Produce the solution. Output ONLY valid JSON matching the schema "
                "described in the system prompt."
            )
            turn = client.send(msg)

            # Write files the model asked to edit (no gate, no verification)
            import os as _os
            success = False
            changed = []
            for action in turn.actions:
                if action.kind == "edit" and action.path and action.content:
                    target = ws / action.path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(action.content, encoding="utf-8")
                    changed.append(action.path)
                if action.kind == "done":
                    success = True

            # If at least one file was written, consider baseline "successful"
            if changed:
                success = True

            return TaskResult(
                task_id=task.task_id,
                mode="baseline",
                success=success,
                gate_decision="none",
                gate_state="none",
                attempts=1,
                input_tokens=turn.input_tokens,
                output_tokens=turn.output_tokens,
                cost_micro_usd=(
                    (turn.input_tokens * 75 + turn.output_tokens * 300) // 1_000_000
                ),
                duration_ms=turn.duration_ms,
                changed_files=changed,
                error=None,
            )
        except Exception as exc:  # noqa: BLE001
            return TaskResult(
                task_id=task.task_id,
                mode="baseline",
                success=False,
                gate_decision="error",
                gate_state="error",
                attempts=1,
                input_tokens=0,
                output_tokens=0,
                cost_micro_usd=0,
                duration_ms=0,
                changed_files=[],
                error=str(exc),
            )

    # ------------------------------------------------------------------

    def _save(self, results: list[TaskResult], summary: dict) -> None:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        doc = {
            "schema_version": 1,
            "model": self.model,
            "mode": "baseline" if self.baseline else "harness",
            "tasks": [asdict(r) for r in results],
            "summary": summary,
        }
        self.output_path.write_text(json.dumps(doc, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _summarise(results: list[TaskResult]) -> dict:
    n = len(results)
    if n == 0:
        return {}
    successes  = sum(1 for r in results if r.success)
    total_in   = sum(r.input_tokens   for r in results)
    total_out  = sum(r.output_tokens  for r in results)
    total_cost = sum(r.cost_micro_usd for r in results)
    total_ms   = sum(r.duration_ms    for r in results)
    attempts   = [r.attempts for r in results]
    return {
        "total_tasks"          : n,
        "success_count"        : successes,
        "success_rate_pct"     : round(successes / n * 100, 1),
        "total_input_tokens"   : total_in,
        "total_output_tokens"  : total_out,
        "total_cost_micro_usd" : total_cost,
        "avg_cost_micro_usd"   : total_cost // n if n else 0,
        "avg_duration_ms"      : total_ms // n if n else 0,
        "avg_attempts"         : round(sum(attempts) / n, 2) if n else 0,
        "max_attempts"         : max(attempts) if attempts else 0,
    }


def _print_task_result(r: TaskResult) -> None:
    ok = "✓" if r.success else "✗"
    print(f"  [{ok}] {r.task_id}: {r.gate_decision}/{r.gate_state} "
          f"attempts={r.attempts} tokens={r.input_tokens+r.output_tokens}")
    if r.error:
        print(f"       error: {r.error[:120]}")


def _print_summary(s: dict) -> None:
    print("\n=== Benchmark Summary ===")
    for k, v in s.items():
        print(f"  {k:<30} {v}")
