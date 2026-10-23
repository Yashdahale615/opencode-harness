"""Root conftest.py - exclude legacy script-style test files."""
collect_ignore_glob = [
    "tests/unit/test_all.py",
    "tests/security/test_more.py",
]
