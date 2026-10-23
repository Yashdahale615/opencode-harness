# integration/

Reserved for tests that exercise the full controller sequence (permission
check -> execution -> snapshot -> verification -> reconciliation -> gate ->
receipt) end to end, as opposed to tests/unit (single-module) or
tests/security (adversarial: symlinks, TOCTOU, tampering, process-group
kills - see tests/security/test_more.py).

No integration tests exist yet in this skeleton; test_all.py in tests/unit
exercises most modules but calls them directly rather than through
harness.controller.
