"""Unit tests for harness.permission.policy."""
import pytest
from harness.permission.policy import (
    Rule,
    ToolRequest,
    Verdict,
    classify_risk,
    evaluate,
)


# ---------------------------------------------------------------------------
# classify_risk
# ---------------------------------------------------------------------------

def test_classify_high_rm():
    req = ToolRequest("shell", ("/bin/rm", "-rf", "/"))
    assert classify_risk(req) == "high"


def test_classify_high_sudo():
    req = ToolRequest("shell", ("/usr/bin/sudo", "whoami"))
    assert classify_risk(req) == "high"


def test_classify_medium_shell():
    req = ToolRequest("shell", ("/usr/bin/pytest",))
    assert classify_risk(req) == "medium"


def test_classify_high_git_push():
    req = ToolRequest("shell", ("/usr/bin/git", "push"))
    assert classify_risk(req) == "high"


def test_classify_high_git_reset():
    req = ToolRequest("shell", ("/usr/bin/git", "reset"))
    assert classify_risk(req) == "high"


def test_classify_medium_git_status():
    req = ToolRequest("shell", ("/usr/bin/git", "status"))
    assert classify_risk(req) == "medium"


def test_classify_low_edit():
    req = ToolRequest("edit", path="src/main.py")
    assert classify_risk(req) == "low"


def test_classify_high_edit_git():
    req = ToolRequest("edit", path=".git/config")
    assert classify_risk(req) == "high"


def test_classify_high_mcp():
    req = ToolRequest("mcp:server.tool")
    assert classify_risk(req) == "high"


# ---------------------------------------------------------------------------
# evaluate — default deny
# ---------------------------------------------------------------------------

def test_default_deny():
    req = ToolRequest("shell", ("/usr/bin/anything",))
    assert evaluate((), req) == Verdict.DENY


def test_default_deny_edit():
    req = ToolRequest("edit", path="src/foo.py")
    assert evaluate((), req) == Verdict.DENY


# ---------------------------------------------------------------------------
# evaluate — first match wins
# ---------------------------------------------------------------------------

def test_allow_pytest():
    rules = (
        Rule("shell", "pytest", Verdict.ALLOW),
        Rule("shell", "*", Verdict.DENY),
    )
    req = ToolRequest("shell", ("/usr/bin/pytest",))
    assert evaluate(rules, req) == Verdict.ALLOW


def test_deny_overrides_later_allow():
    rules = (
        Rule("shell", "*", Verdict.DENY),
        Rule("shell", "pytest", Verdict.ALLOW),
    )
    req = ToolRequest("shell", ("/usr/bin/pytest",))
    assert evaluate(rules, req) == Verdict.DENY  # first match = DENY


def test_ask_rule():
    rules = (Rule("shell", "git", Verdict.ASK),)
    req = ToolRequest("shell", ("/usr/bin/git", "status"))
    assert evaluate(rules, req) == Verdict.ASK


def test_edit_glob_match():
    rules = (Rule("edit", "src/*", Verdict.ALLOW),)
    assert evaluate(rules, ToolRequest("edit", path="src/a.py")) == Verdict.ALLOW
    assert evaluate(rules, ToolRequest("edit", path="tests/t.py")) == Verdict.DENY


def test_tool_glob_mismatch():
    rules = (Rule("shell", "pytest", Verdict.ALLOW),)
    req = ToolRequest("edit", path="pytest")   # tool is "edit", not "shell"
    assert evaluate(rules, req) == Verdict.DENY


# ---------------------------------------------------------------------------
# Wildcard tool glob
# ---------------------------------------------------------------------------

def test_wildcard_tool_glob():
    rules = (Rule("*", "*", Verdict.ALLOW),)
    assert evaluate(rules, ToolRequest("shell", ("/bin/rm",))) == Verdict.ALLOW
    assert evaluate(rules, ToolRequest("edit", path="x.py")) == Verdict.ALLOW
