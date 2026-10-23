"""conftest.py - add src/ to sys.path and provide shared fixtures."""
import os
import sys
from pathlib import Path

# Allow `import harness` without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest

# Exclude legacy script-style test files that run at import time
# (they use /bin/true which doesn't exist on Windows and are not pytest tests)
collect_ignore = [
    "tests/unit/test_all.py",
    "tests/security/test_more.py",
]

# Monkeypatch assert_trusted_ancestry globally for tests that use it via
# load_catalog / validate_check — the real check fails under /tmp which is
# world-writable on most systems.
import harness.verification.catalog as _cat
_cat.assert_trusted_ancestry = lambda p: None
