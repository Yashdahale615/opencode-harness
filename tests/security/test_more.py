
"""Cross-platform tests for verification runtime behavior."""

import os
import pathlib
import shutil
import sys
import tempfile

import harness.verification.catalog as C
from harness.verification.catalog import CheckSpec
from harness.verification.runtime import run_check, aggregate

# Test-only override: isolate runtime behavior from host ancestry policy.
C.assert_trusted_ancestry = lambda p: None

tmp = pathlib.Path(tempfile.mkdtemp()).resolve()
ws = tmp / "ws"
ws.mkdir()


def spec(argv, timeout=5):
    return CheckSpec(
        "c1",
        tuple(str(arg) for arg in argv),
        ".",
        ("*",),
        1,
        timeout,
        ("PATH",),
        (),
    )


python = str(pathlib.Path(sys.executable).resolve())

# 1. Successful executable
r = run_check(
    spec([python, "-c", "pass"]),
    ws,
)
print("success:", r.status.value, r.reason[:50])

# 2. Non-zero exit
r = run_check(
    spec([python, "-c", "raise SystemExit(1)"]),
    ws,
)
print("failure:", r.status.value, r.reason[:50])

# 3. Timeout
r = run_check(
    spec([python, "-c", "import time; time.sleep(5)"], timeout=1),
    ws,
)
print("timeout:", r.status.value, r.reason[:50])

# 4. Non-existent executable
missing = tmp / ("missing.exe" if os.name == "nt" else "missing")
r = run_check(
    spec([str(missing)]),
    ws,
)
print("missing:", r.status.value, r.reason[:50])

# 5. Non-zero exit with an explicit error code
r = run_check(
    spec([python, "-c", "raise SystemExit(3)"]),
    ws,
)
print("exit 3:", r.status.value, r.reason[:50])

# 6. Executable located inside the workspace.
# Copy the current interpreter so the path exists and is a real executable.
inside_exe = ws / ("python.exe" if os.name == "nt" else "python")
shutil.copy2(python, inside_exe)

r = run_check(
    spec([str(inside_exe)]),
    ws,
)
print("inside ws:", r.status.value, r.reason[:60])

# Aggregate successful and failed verification results.
ok = run_check(spec([python, "-c", "pass"]), ws)
bad = run_check(
    spec([python, "-c", "raise SystemExit(1)"]),
    ws,
)

print(
    "aggregate:",
    aggregate([ok]),
    aggregate([ok, bad]),
    aggregate([ok], ["docs/a"]),
    aggregate([ok], ["docs/a"], ["docs/*"]),
    aggregate([]),
)
