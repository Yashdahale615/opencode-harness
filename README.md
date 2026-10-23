# OpenCode Harness with Google Gemini

A **verified-execution harness** that runs coding tasks through
[Google Gemini](https://ai.google.dev/) with a deterministic permission gate,
independent verification, evidence receipts, and a reproducible benchmark.

```
User Input ──► Harness Init ──► OpenCode + Gemini ──► Permission Gate
                                                              │
                                                    ┌─────────▼──────────┐
                                                    │  Controlled Exec   │
                                                    └─────────┬──────────┘
                                                              │
                                               ┌─────────────▼─────────────┐
                                               │  Independent Verification │
                                               └─────────────┬─────────────┘
                                                             │
                                         ┌───────────────────▼──────────────────┐
                                         │          Acceptance Gate             │
                                         │  PASS ──► evidence + receipt         │
                                         │  FAIL ──► send diagnostics → retry   │
                                         └──────────────────────────────────────┘
                                                             │
                                               ┌─────────────▼──────────┐
                                               │  Evidence & Report     │
                                               └────────────────────────┘
```

---

## Quick Start

### 1. Prerequisites

```bash
python --version   # Python 3.10+
pip install -e ".[dev]"
```

### 2. Set your Gemini API key

```bash
# Windows PowerShell
$env:GEMINI_API_KEY = "your-key-here"

# Linux / macOS
export GEMINI_API_KEY="your-key-here"
```

> **Never hardcode the key.** The harness reads it exclusively from the
> environment variable `GEMINI_API_KEY`.

### 3. Run a task

```bash
harness-run "Add a function that reverses a string" path/to/workspace
```

With options:

```bash
harness-run "write a fibonacci function" ./my-project \
  --model gemini-1.5-flash \
  --max-attempts 4 \
  --allow-shell pytest \
  --allow-shell python \
  --profile profiles/default.yaml \
  --output-dir ./run-output
```

---

## CLI Reference

### `harness-run` — execute a task

```
harness-run TASK WORKSPACE [options]

Arguments:
  TASK          The coding task description (plain English).
  WORKSPACE     Path to the repository / directory to work in.

Options:
  --model TEXT             Gemini model name (default: gemini-1.5-flash)
  --profile PATH           Path to a profile YAML file
  --catalog PATH           Path to trusted verification catalog JSON
  --max-attempts INT       Maximum repair attempts (default: 4)
  --output-dir PATH        Directory for traces and reports
  --allow-shell GLOB       Shell command basename to ALLOW (repeatable)
  --non-interactive        Never prompt; ASK_USER → BLOCKED
  --dry-run                Print config and exit
```

### `harness-verify` — run checks against a catalog

```
harness-verify WORKSPACE CATALOG [--changed FILE ...]
```

### `harness-inspect` — read a trace or report

```
harness-inspect PATH [--verify-chain]
```

### `harness-evaluate` — summarise a completed run

```
harness-evaluate REPORT_JSON WORKSPACE
```

### `harness-bench` — run the benchmark suite

```
harness-bench TASKS_JSONL WORKSPACE_TEMPLATE \
  --model gemini-1.5-flash \
  --output evals/reports/benchmark.json \
  [--baseline]
```

---

## Architecture

```
src/harness/
├── contracts/core.py        Trust foundation: enums, fingerprint, safe_id
├── permission/policy.py     Default-deny permission gate
├── workspace/
│   ├── snapshot.py          Before/after snapshots, workspace fingerprint
│   └── paths.py             Symlink-safe path resolution
├── verification/
│   ├── catalog.py           Trusted catalog loading + identity validation
│   ├── select.py            Scope/cost-based check selection
│   └── runtime.py           Run checks, aggregate results
├── gate/
│   ├── decision.py          PURE gate decide() function
│   └── reconcile.py         Post-verification snapshot reconciliation
├── evidence/receipt.py      Evidence, receipt, verify_receipt
├── observability/trace.py   Hash-chained append-only trace log
├── orchestration/state.py   RunState machine + Budget
├── context/select.py        Budgeted context selection
├── models/route.py          Profile-based model routing
├── llm/gemini.py            Google Gemini adapter + response parser
├── controller.py            End-to-end run loop (main orchestrator)
├── benchmark/runner.py      Benchmark harness vs baseline
└── entry.py                 CLI entry points
```

### Run Loop

1. **Snapshot** the workspace before anything changes.
2. **Ask Gemini** for a plan (edit / shell / read / done actions).
3. **Permission-check** every action before execution.
4. **Execute** approved actions; record results in the hash-chained trace.
5. **Snapshot** again; compute diff of changed files.
6. **Run verification** checks from the trusted catalog against changed files.
7. **Reconcile** — did verification itself mutate the workspace?
8. **Gate** — `decide(GateInput)` is a **pure function** that returns
   ALLOWED, BLOCKED, or ASK_USER based on the evidence.
9. If BLOCKED and budget allows → send diagnostics back to Gemini and retry.
10. **Build evidence receipt** and write `report.json`.

---

## Permission Model

Rules are evaluated first-match-wins. Default is **DENY** when no rule matches.

```python
from harness.permission.policy import Rule, Verdict

rules = (
    Rule("shell", "pytest",  Verdict.ALLOW),
    Rule("shell", "python",  Verdict.ALLOW),
    Rule("shell", "git",     Verdict.ASK),    # requires human approval
    Rule("edit",  "*",       Verdict.ALLOW),  # all file edits allowed
    # everything else: DENY  ← default, cannot be changed
)
```

Risk levels: `high` (rm, sudo, curl, git push, …), `medium` (shell), `low` (edit).

---

## Profiles

| Profile | `allow_unverified_low_risk` | `max_reverify` | Notes |
|---------|--------------------------|----------------|-------|
| `safe` | false | 0 | strictest |
| `default` | false | 2 | balanced |
| `autonomous` | true | 5 | for trusted CI |
| `benchmark` | false | 2 | non-interactive |

---

## Verification Catalog

A **catalog** is a JSON file that lives **outside** the workspace and
declares trusted check commands. The harness verifies the command's
identity (SHA-256 of the binary, ancestry ownership) and any
`immutable_inputs` (config files the agent must not weaken) before running
it.

```json
{
  "schema_version": 1,
  "checks": [{
    "check_id": "pytest",
    "argv": ["C:/Python310/python.exe", "-m", "pytest", "--tb=short", "-q"],
    "cwd": ".",
    "scope": ["src/*", "tests/*"],
    "cost_rank": 1,
    "timeout_seconds": 120,
    "env_allow": ["PATH", "PYTHONPATH"],
    "immutable_inputs": {
      "pyproject.toml": "<sha256-hex-of-pyproject.toml>"
    }
  }]
}
```

Get the SHA-256 of a file:

```bash
python -c "import hashlib; print(hashlib.sha256(open('pyproject.toml','rb').read()).hexdigest())"
```

---

## Benchmarking

Compare baseline Gemini (raw output, no gate) against the full harness
using the same model and task set.

```bash
# Harness run
harness-bench benchmarks/tasks/sample_tasks.jsonl benchmarks/workspace-template/ \
  --model gemini-1.5-flash \
  --output evals/reports/harness.json

# Baseline run (no gate, no verification)
harness-bench benchmarks/tasks/sample_tasks.jsonl benchmarks/workspace-template/ \
  --model gemini-1.5-flash \
  --output evals/reports/baseline.json \
  --baseline
```

### Task file format (`tasks.jsonl`)

One JSON object per line:

```json
{"task_id": "hello-world", "description": "Create hello.py that prints Hello World", "expected_files": ["hello.py"]}
```

### Metrics collected

- `success_rate_pct` — fraction of tasks that passed the gate
- `avg_attempts` — average repair iterations
- `total_input_tokens`, `total_output_tokens`
- `avg_cost_micro_usd` — estimated cost in micro-USD
- `avg_duration_ms`

---

## Running Tests

```bash
# Unit tests
python -m pytest tests/unit/ -v

# Security tests  
python -m pytest tests/security/ -v

# All tests (excluding legacy script)
python -m pytest tests/unit/ tests/security/ -v

# Legacy script tests (Unix only)
python tests/unit/test_all.py
python tests/security/test_more.py
```

---

## Security Model

See `SECURITY.md` and `docs/security.md`.

Key invariants enforced by the test suite:

1. `gate/decision.py:decide()` is a **pure function** — no I/O, clock, or randomness.
2. `permission/policy.py:evaluate()` returns **DENY** when no rule matches.
3. `verification/catalog.py:assert_trusted_ancestry` validates ownership of every
   ancestor of the check executable (Unix only; skipped on Windows).
4. Trace is **hash-chained** — any tamper is detected by `verify_chain()`.
5. Receipts are **workspace-bound** — a receipt from run A cannot be applied to
   workspace B.

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GEMINI_API_KEY` | Yes | Google Gemini API key |

---

## Limitations

- **Windows**: `resource` limits (CPU, file size, process count) are not
  applied on Windows because `resource` is a POSIX-only module. Process
  containment on Windows is best-effort.
- **Trust ancestry check**: On Windows, `assert_trusted_ancestry` is a no-op
  because POSIX ownership semantics don't apply.
- **Symlink TOCTOU**: The `open_beneath` hardened path opener is Unix-only.
  On Windows, `resolve_inside` provides advisory protection only.
- **Token costs**: Cost estimates are based on published Gemini Flash pricing
  at time of writing ($0.075/1M input, $0.30/1M output). Verify current
  pricing at https://ai.google.dev/pricing.
- **API key format**: Standard Gemini API keys begin with `AIza`. Keys
  beginning with `AQ.` are service-account tokens for the Vertex AI endpoint,
  which requires a different client configuration.

---

## Project Layout

```
opencode-harness/
├── src/harness/          Python package (pip install -e ".[dev]")
├── commands/             Thin CLI wrappers (also callable as Python modules)
├── tests/
│   ├── unit/             156 unit tests covering all modules
│   └── security/         Adversarial tests: tamper detection, escape prevention
├── benchmarks/tasks/     Sample task JSONL files
├── evals/reports/        Benchmark output (machine-readable JSON)
├── profiles/             Acceptance policy presets
├── docs/                 Architecture, security, verification documentation
└── AGENTS.md             Instructions for agents working in this repo
```
