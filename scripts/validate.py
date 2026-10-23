#!/usr/bin/env python3
"""scripts/validate.py - run the checked-in test scripts and report status.

Stub aggregator over tests/unit/test_all.py and tests/security/test_more.py
until those are converted to real pytest cases (see tests/*/README.md).
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = [ROOT / "tests/unit/test_all.py", ROOT / "tests/security/test_more.py"]

def main() -> int:
    ok = True
    for s in SCRIPTS:
        print(f"--- {s.relative_to(ROOT)} ---")
        r = subprocess.run([sys.executable, str(s)])
        ok = ok and r.returncode == 0
    return 0 if ok else 1

if __name__ == "__main__":
    raise SystemExit(main())
