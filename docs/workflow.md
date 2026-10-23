# Harness Workflow

Complete workflow of the OpenCode + Gemini Agent Harness — from user input to final report.

---

## Workflow Diagram

```mermaid
flowchart TD
    A([👤 User Input\nProvide coding task + workspace path]) --> B

    B[⚙️ Harness Initialization\nLoad profile · Set permissions · Snapshot workspace] --> C

    C[🤖 Gemini LLM\nAnalyze task · Generate code · Propose actions\nedit / shell / read / done] --> D

    D{🛡️ Permission Gate\nCheck every action}

    D -->|ALLOW\nSafe action| E
    D -->|ASK\nRisky action| F
    D -->|DENY\nDangerous action| G

    F{👤 Human Approval?}
    F -->|Yes| E
    F -->|No| G

    G[🚫 Action Blocked\nLog violation + increment counter] --> H

    E[✅ Execute Action\nWrite file · Run command · Read file] --> H

    H[📸 Snapshot Workspace\nRecord all file changes] --> I

    I[🔍 Independent Verification\nRun trusted checks from catalog\npytest · linter · build] --> J

    J[🔄 Reconcile\nDid verification change the workspace?] --> K

    K{⚖️ Acceptance Gate\ndecide GateInput}

    K -->|allowed\nverified_and_reconciled| L
    K -->|allowed\nunverified_low_risk| L
    K -->|ask_user\nno_trusted_check| M
    K -->|blocked\nverification_failed| N
    K -->|blocked\npermission_violation| N
    K -->|reverify\nstate_changed| I

    M{👤 Human Decision?}
    M -->|Accept| L
    M -->|Reject| N

    N{🔁 Retry Budget?}
    N -->|attempts remaining| O
    N -->|budget exhausted| P

    O[📋 Send Diagnostics to Gemini\nError output · Failed checks · Stderr] --> C

    L[🎉 SUCCESS\nAccept changes] --> Q
    P[💥 FAILURE\nReject all changes] --> Q

    Q[📄 Evidence + Report\nreceipt.json · report.json · trace.jsonl]

    style A fill:#4A90D9,color:#fff
    style B fill:#7B68EE,color:#fff
    style C fill:#2E8B57,color:#fff
    style D fill:#FF8C00,color:#fff
    style E fill:#2E8B57,color:#fff
    style F fill:#FF8C00,color:#fff
    style G fill:#DC143C,color:#fff
    style H fill:#7B68EE,color:#fff
    style I fill:#2E8B57,color:#fff
    style J fill:#7B68EE,color:#fff
    style K fill:#FF8C00,color:#fff
    style L fill:#228B22,color:#fff
    style M fill:#FF8C00,color:#fff
    style N fill:#DC143C,color:#fff
    style O fill:#4A90D9,color:#fff
    style P fill:#DC143C,color:#fff
    style Q fill:#4A90D9,color:#fff
```

---

## Step-by-Step Explanation

### Step 1 — User Input
You provide two things:
- A **task** in plain English — e.g. `"Create a Flask web app with home and login page"`
- A **workspace path** — the folder where files will be created — e.g. `C:\Temp\myproject`

```powershell
python -m harness.entry "YOUR TASK" C:\Temp\myproject --non-interactive --profile profiles/autonomous.yaml
```

---

### Step 2 — Harness Initialization
The harness:
- Loads your **profile** (`safe` / `default` / `autonomous` / `benchmark`)
- Sets **permission rules** — which commands are ALLOW / ASK / DENY
- Takes a **before snapshot** of the workspace (SHA-256 fingerprint of every file)

---

### Step 3 — Gemini LLM
Gemini receives your task and responds with a structured JSON plan:

```json
{
  "explanation": "I will create hello.py with a print statement",
  "actions": [
    { "kind": "edit", "path": "hello.py", "content": "print('Hello World')" },
    { "kind": "done" }
  ]
}
```

Action types Gemini can propose:

| Kind | What it does |
|------|-------------|
| `edit` | Create or modify a file |
| `read` | Read a file for context |
| `shell` | Run a terminal command |
| `done` | Task is complete |

---

### Step 4 — Permission Gate
**Every single action** is checked before execution:

| Verdict | When | Example |
|---------|------|---------|
| ✅ ALLOW | Safe, matches a rule | `edit *.py` |
| ❓ ASK | Risky, needs human approval | `git push` |
| ❌ DENY | Dangerous, no rule matches | `rm -rf /` |

Default is **DENY** — if no rule matches, the action is blocked.

---

### Step 5 — Controlled Execution
Only approved actions run. Each execution is:
- Logged with timestamp
- Recorded in the tamper-proof trace
- Limited by timeouts and resource limits

---

### Step 6 — Independent Verification
After execution, the harness runs **trusted checks** from a catalog (if provided):
- `pytest` — runs your test suite
- Linters — checks code quality
- Build checks — confirms the code compiles/runs

These checks run **independently of Gemini** — Gemini cannot fake a passing test.

---

### Step 7 — Acceptance Gate
A **pure function** (`decide()`) makes the final call based purely on evidence:

| Decision | State | Meaning |
|----------|-------|---------|
| ✅ `allowed` | `verified_and_reconciled` | Tests passed, changes accepted |
| ✅ `allowed` | `unverified_low_risk` | No tests but low-risk change, auto-approved |
| ❓ `ask_user` | `no_trusted_check` | No test catalog, needs human approval |
| ❌ `blocked` | `verification_failed` | Tests failed |
| ❌ `blocked` | `permission_violation` | Gemini tried something dangerous |

---

### Step 8 — Repair Loop
If blocked and retry budget allows:
- Harness sends **diagnostics** (error output, failed test results) back to Gemini
- Gemini analyzes the failure and proposes a fix
- Loop repeats up to `max_attempts` times (default: 4)

---

### Step 9 — Evidence and Report
Every run produces 3 files inside `.harness/job-xxxxx/`:

| File | What it contains |
|------|-----------------|
| `report.json` | Final decision, changed files, token usage, cost |
| `trace.jsonl` | Every action step-by-step, hash-chained (tamper-proof) |
| Receipt in report | SHA-256 fingerprint binding the decision to the exact workspace state |

---

## Output Folder Structure

```
C:\Temp\myproject\
├── hello.py                        ← file Gemini created
└── .harness\
    └── job-abc123\
        ├── report.json             ← check this first
        └── trace.jsonl             ← full step-by-step log
```

---

## Quick Reference Commands

```powershell
# Set API key
$env:GEMINI_API_KEY = "your-key-here"

# Run a task
python -m harness.entry "YOUR TASK" C:\Temp\myproject --non-interactive --allow-shell python --profile profiles/autonomous.yaml

# Check result
Get-Content "C:\Temp\myproject\.harness\$(Get-ChildItem C:\Temp\myproject\.harness | Select-Object -Last 1 -ExpandProperty Name)\report.json"

# Run created file
python C:\Temp\myproject\hello.py

# Run all tests
python -m pytest tests/ -q
```
