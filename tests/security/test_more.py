import os, json, hashlib, pathlib, tempfile
import harness.verification.catalog as C
C.assert_trusted_ancestry = lambda p: None
from harness.verification.catalog import *
from harness.verification.runtime import *
from harness.contracts.core import VerificationStatus as VS
tmp=pathlib.Path(tempfile.mkdtemp()); ws=tmp/"ws"; ws.mkdir()
def spec(argv, t=5): return CheckSpec("c1", tuple(argv), ".", ("*",), 1, t, ("PATH",), ())
for a,t in [(["/bin/true"],5),(["/bin/false"],5),(["/bin/sleep","5"],1),(["/nonexistent/x"],5),(["/bin/sh","-c","exit 3"],5),(["/tmp/ws-inside"],5)]:
    r=run_check(spec(a,t),ws); print(a[-1], r.status.value, r.reason[:50])
sp=ws/"evil.sh"; sp.write_text("#!/bin/sh\nexit 0\n"); sp.chmod(0o755)
r=run_check(spec([str(sp)]),ws); print("inside ws:", r.status.value, r.reason[:60])
ok=run_check(spec(["/bin/true"]),ws); bad=run_check(spec(["/bin/false"]),ws)
print(aggregate([ok]), aggregate([ok,bad]), aggregate([ok],["docs/a"]), aggregate([ok],["docs/a"],["docs/*"]), aggregate([]))
