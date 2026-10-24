
"""Integration-style checks for core harness components."""
import hashlib
import json
import os
import pathlib
import shutil
import sys
import tempfile

from harness.contracts.core import *
from harness.workspace.snapshot import *
from harness.verification.catalog import *
from harness.verification.select import *
from harness.gate.decision import *
from harness.gate.reconcile import *
from harness.orchestration.state import *
from harness.permission.policy import *
from harness.observability.trace import *
from harness.evidence.receipt import *
from harness.context.select import *
from harness.models.route import *


# Workspace and immutable input.
tmp = pathlib.Path(tempfile.mkdtemp()).resolve()
ws = tmp / "ws"
ws.mkdir()
(ws / "pytest.ini").write_bytes(b"[pytest]\n")

(ws / "src").mkdir()
(ws / "src" / "a.py").write_text("x=1", encoding="utf-8")

trusted = tmp / "trusted"
trusted.mkdir()

# This script's POSIX trust-ancestry test assumes a Linux /tmp directory.
os.chmod(trusted, 0o755)
os.chmod(tmp, 0o755)

if os.name != "nt":
    # On POSIX, /tmp is commonly world-writable and should be rejected.
    cat = {
        "schema_version": 1,
        "checks": [{
            "check_id": "unit",
            "argv": [shutil.which("true") or "/bin/true"],
            "cwd": ".",
            "scope": ["src/*", "tests/*"],
            "cost_rank": 1,
            "timeout_seconds": 60,
            "env_allow": ["PATH"],
            "immutable_inputs": {
                "pytest.ini": hashlib.sha256(b"[pytest]\n").hexdigest()
            },
        }],
    }

    (trusted / "catalog.json").write_text(
        json.dumps(cat), encoding="utf-8"
    )

    try:
        load_catalog(trusted / "catalog.json", ws)
        print("catalog under /tmp accepted?!")
    except TrustError as exc:
        print("ok (expected, /tmp writable):", exc)
else:
    # Windows skips POSIX ownership/mode-bit ancestry validation.
    cat = {
        "schema_version": 1,
        "checks": [{
            "check_id": "unit",
            "argv": [str(pathlib.Path(sys.executable).resolve())],
            "cwd": ".",
            "scope": ["src/*", "tests/*"],
            "cost_rank": 1,
            "timeout_seconds": 60,
            "env_allow": ["PATH"],
            "immutable_inputs": {
                "pytest.ini": hashlib.sha256(b"[pytest]\n").hexdigest()
            },
        }],
    }

    (trusted / "catalog.json").write_text(
        json.dumps(cat), encoding="utf-8"
    )

# Bypass ancestry only while testing the remaining catalog behavior.
import harness.verification.catalog as C

original_ancestry_check = C.assert_trusted_ancestry
C.assert_trusted_ancestry = lambda p: None

try:
    c = load_catalog(trusted / "catalog.json", ws)
    print(c.fingerprint[:20], len(c.checks))

    try:
        load_catalog(ws / "pytest.ini", ws)
    except TrustError as exc:
        print("ok:", exc)
    else:
        raise AssertionError("Catalog inside workspace was accepted")

    fp = validate_check(c.checks[0], ws)
    print(fp[:20])

    # Alter immutable input using exact bytes to avoid Windows newline changes.
    (ws / "pytest.ini").write_bytes(
        b"[pytest]\naddopts=-k nothing\n"
    )

    try:
        validate_check(c.checks[0], ws)
    except TrustError as exc:
        print("ok (expected immutable-input rejection):", exc)
    else:
        raise AssertionError("Modified immutable input was accepted")

    sel, unc = select_checks(
        c.checks, ("src/a.py", "docs/x.md")
    )
    print([s.check_id for s in sel], unc)

finally:
    C.assert_trusted_ancestry = original_ancestry_check


# Gate
P = AcceptancePolicy()


def g(**kw):
    base = dict(
        run_succeeded=True,
        workspace_changed=True,
        permission_violations=0,
        risk="medium",
        verification=VerificationStatus.PASSED,
        reconciled_unchanged=True,
        reverify_count=0,
        policy=P,
    )
    base.update(kw)
    return decide(GateInput(**base))


print(g().state, g().decision)
print(g(run_succeeded=False).state)
print(g(workspace_changed=False).state)
print(
    g(verification=None).decision,
    g(
        verification=None,
        risk="low",
        policy=AcceptancePolicy(True),
    ).decision,
)
print(g(verification=VerificationStatus.FAILED).decision)
print(g(verification=VerificationStatus.UNAVAILABLE).state)
print(
    g(reconciled_unchanged=False).state,
    g(reconciled_unchanged=False, reverify_count=2).reasons,
)
print(g(reconciled_unchanged=None).reasons)


# State machine
m = RunMachine()
m.go(S.CONTEXT_READY)

try:
    m.go(S.TERMINAL_VERIFIED)
except IllegalTransition as exc:
    print("ok:", exc)

b = Budget(1000, 500, 2)

try:
    b.charge(2000)
except BudgetExceeded:
    print("ok budget")


# Permission
rules = (
    Rule("shell", "git", Verdict.ASK),
    Rule("shell", "pytest", Verdict.ALLOW),
    Rule("edit", "src/*", Verdict.ALLOW),
)

print(
    evaluate(rules, ToolRequest("shell", ("git",))),
    evaluate(rules, ToolRequest("shell", ("/usr/bin/rm", "-rf"))),
    evaluate(rules, ToolRequest("edit", path="src/a.py")),
    classify_risk(ToolRequest("shell", ("/bin/rm",))),
)


# Trace integrity
tp = tmp / "t.jsonl"
tw = TraceWriter(tp, "job-1")
tw.emit("start", {"a": 1})
tw.emit("tool", {"latency_ms": 12})
tw.close()

print("chain ok", verify_chain(tp))

lines = tp.read_bytes().splitlines()
ev = json.loads(lines[0])
ev["data"]["a"] = 2
tp.write_bytes(
    json.dumps(ev).encode() + b"\n" + lines[1] + b"\n"
)

try:
    verify_chain(tp)
except ContractError as exc:
    print("ok:", exc)


# Receipt integrity
e = Evidence(
    "ev-1", "verification", 1, "sha256:aa",
    {"status": "passed"}, now_ts()
)

r = build_receipt(
    job_id="job-1",
    session_id="s-1",
    decision=GateDecision.ALLOWED,
    evidence=[e],
    catalog_fp="sha256:c",
    command_fps=["sha256:d"],
    workspace_fp="sha256:aa",
    policy_fp="sha256:p",
    mutation_revision=1,
)

verify_receipt(r, current_workspace_fp="sha256:aa")

try:
    verify_receipt(r, current_workspace_fp="sha256:bb")
except ContractError as exc:
    print("ok:", exc)

r2 = dict(r)
r2["decision"] = "allowed"
r2["catalog_fp"] = "sha256:zzz"

try:
    verify_receipt(r2, current_workspace_fp="sha256:aa")
except ContractError as exc:
    print("ok:", exc)


# Context selection
items = [
    ContextItem("task", "t", 0, 100),
    ContextItem("file:a", "a", 1, 500),
    ContextItem("file:b", "b", 2, 900),
    ContextItem("readme", "r", 3, 400),
]

ch, used, fp = select_context(items, 1100)
print([i.key for i in ch], used, fp[:15])


# Routing
ps = {
    "core": Profile("core", "m-core", 100000, 10, 1),
    "deep": Profile("deep", "m-deep", 200000, 50, 2),
    "orchestration": Profile("orchestration", "m-orch", 100000, 30, 2),
}

print(
    route(ps, TaskFeatures(2, 1, 20000, False, 10**6)).name,
    route(ps, TaskFeatures(1, 0, 20000, False, 10**6)).name,
)

try:
    route(ps, TaskFeatures(3, 2, 20000, False, 900))
except ValueError as exc:
    print("ok:", exc)
