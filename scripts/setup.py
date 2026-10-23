#!/usr/bin/env python3
"""scripts/setup.py - dev environment bootstrap.

Stub: installs the package in editable mode with dev extras. Prefer
`pip install -e ".[dev]"` directly; this exists as a scriptable hook for CI
or onboarding docs to call.
"""
import subprocess
import sys

def main() -> int:
    return subprocess.call([sys.executable, "-m", "pip", "install", "-e", ".[dev]",
                             "--break-system-packages"])

if __name__ == "__main__":
    raise SystemExit(main())
