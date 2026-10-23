import json, os, pathlib, stat, tempfile, hashlib, sys
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

tmp = pathlib.Path(tempfile.mkdtemp())
ws = tmp/"ws"; ws.mkdir(); (ws/"pytest.ini").write_text("[pytest]\n")
(ws/"src").mkdir(); (ws/"src/a.py").write_text("x=1")
trusted = tmp/"trusted"; trusted.mkdir(); os.chmod(trusted,0o755); os.chmod(tmp,0o755)
# ancestry of tmp itself: /tmp is sticky world-writable -> must be rejected!
cat = {"schema_version":1,"checks":[{"check_id":"unit","argv":["/bin/true"],"cwd":".",
  "scope":["src/*","tests/*"],"cost_rank":1,"timeout_seconds":60,"env_allow":["PATH"],
  "immutable_inputs":{"pytest.ini":hashlib.sha256(b"[pytest]\n").hexdigest()}}]}
(trusted/"catalog.json").write_text(json.dumps(cat))
try: load_catalog(trusted/"catalog.json", ws); print("catalog under /tmp accepted?!")
except TrustError as e: print("ok (expected, /tmp writable):", e)

# bypass ancestry to test rest: monkeypatch
import harness.verification.catalog as C
C.assert_trusted_ancestry = lambda p: None
c = load_catalog(trusted/"catalog.json", ws); print(c.fingerprint[:20], len(c.checks))
try: load_catalog(ws/"pytest.ini", ws)
except TrustError as e: print("ok:", e)
fp = validate_check(c.checks[0], ws); print(fp[:20])
(ws/"pytest.ini").write_text("[pytest]\naddopts=-k nothing\n")
try: validate_check(c.checks[0], ws)
except TrustError as e: print("ok:", e)
sel, unc = select_checks(c.checks, ("src/a.py","docs/x.md")); print([s.check_id for s in sel], unc)

# gate
P = AcceptancePolicy()
def g(**kw):
    base = dict(run_succeeded=True, workspace_changed=True, permission_violations=0,
        risk="medium", verification=VerificationStatus.PASSED, reconciled_unchanged=True,
        reverify_count=0, policy=P); base.update(kw); return decide(GateInput(**base))
print(g().state, g().decision)
print(g(run_succeeded=False).state)
print(g(workspace_changed=False).state)
print(g(verification=None).decision, g(verification=None, risk="low", policy=AcceptancePolicy(True)).decision)
print(g(verification=VerificationStatus.FAILED).decision)
print(g(verification=VerificationStatus.UNAVAILABLE).state)
print(g(reconciled_unchanged=False).state, g(reconciled_unchanged=False, reverify_count=2).reasons)
print(g(reconciled_unchanged=None).reasons)

# state machine
m = RunMachine(); m.go(S.CONTEXT_READY)
try: m.go(S.TERMINAL_VERIFIED)
except IllegalTransition as e: print("ok:", e)
b = Budget(1000, 500, 2)
try: b.charge(2000)
except BudgetExceeded: print("ok budget")

# permission
rules = (Rule("shell","git",Verdict.ASK), Rule("shell","pytest",Verdict.ALLOW), Rule("edit","src/*",Verdict.ALLOW))
print(evaluate(rules, ToolRequest("shell",("/usr/bin/pytest",))), evaluate(rules, ToolRequest("shell",("/usr/bin/rm","-rf"))),
      evaluate(rules, ToolRequest("edit",path="src/a.py")), classify_risk(ToolRequest("shell",("/bin/rm",))))
# NOTE: evaluate on edit path uses req.path full path with fnmatch
# trace
tp = tmp/"t.jsonl"; tw = TraceWriter(tp, "job-1"); tw.emit("start", {"a":1}); tw.emit("tool", {"latency_ms":12}); tw.close()
print("chain ok", verify_chain(tp))
lines = tp.read_bytes().splitlines(); ev = json.loads(lines[0]); ev["data"]["a"]=2
tp.write_bytes(json.dumps(ev).encode()+b"\n"+lines[1]+b"\n")
try: verify_chain(tp)
except ContractError as e: print("ok:", e)
# receipt
e = Evidence("ev-1","verification",1,"sha256:aa",{"status":"passed"},now_ts())
r = build_receipt(job_id="job-1", session_id="s-1", decision=GateDecision.ALLOWED, evidence=[e],
    catalog_fp="sha256:c", command_fps=["sha256:d"], workspace_fp="sha256:aa", policy_fp="sha256:p", mutation_revision=1)
verify_receipt(r, current_workspace_fp="sha256:aa")
try: verify_receipt(r, current_workspace_fp="sha256:bb")
except ContractError as ex: print("ok:", ex)
r2 = dict(r); r2["decision"]="allowed"; r2["catalog_fp"]="sha256:zzz"
try: verify_receipt(r2, current_workspace_fp="sha256:aa")
except ContractError as ex: print("ok:", ex)
# context
items=[ContextItem("task","t",0,100),ContextItem("file:a","a",1,500),ContextItem("file:b","b",2,900),ContextItem("readme","r",3,400)]
ch,used,fp=select_context(items,1100); print([i.key for i in ch],used,fp[:15])
# route
ps={"core":Profile("core","m-core",100000,10,1),"deep":Profile("deep","m-deep",200000,50,2),"orchestration":Profile("orchestration","m-orch",100000,30,2)}
print(route(ps,TaskFeatures(2,1,20000,False,10**6)).name, route(ps,TaskFeatures(1,0,20000,False,10**6)).name)
try: route(ps,TaskFeatures(3,2,20000,False,900))
except ValueError as e: print("ok:", e)
