#!/usr/bin/env python3
"""scripts/release.py - release checklist stub.

Not wired to any package index. Intended sequence once this is a real
project: bump version in pyproject.toml, update CHANGELOG.md, tag, build,
publish. Currently just runs validate.py as a release gate.
"""
import subprocess
import sys
from pathlib import Path

def main() -> int:
    validate = Path(__file__).resolve().with_name("validate.py")
    return subprocess.call([sys.executable, str(validate)])

if __name__ == "__main__":
    raise SystemExit(main())
