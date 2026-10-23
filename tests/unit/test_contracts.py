"""Unit tests for harness.contracts.core."""
import pytest
from harness.contracts.core import (
    ContractError,
    GateDecision,
    VerificationStatus,
    Verdict,
    safe_id,
    parse_ts,
    now_ts,
    exact_keys,
    canonical_json,
    fingerprint,
)


# ---------------------------------------------------------------------------
# safe_id
# ---------------------------------------------------------------------------

def test_safe_id_valid():
    assert safe_id("job-1", "x") == "job-1"
    assert safe_id("abc", "x") == "abc"
    assert safe_id("A0", "x") == "A0"


def test_safe_id_rejects_dot():
    with pytest.raises(ContractError):
        safe_id("a.b", "x")


def test_safe_id_rejects_slash():
    with pytest.raises(ContractError):
        safe_id("a/b", "x")


def test_safe_id_rejects_empty():
    with pytest.raises(ContractError):
        safe_id("", "x")


def test_safe_id_rejects_space():
    with pytest.raises(ContractError):
        safe_id("a b", "x")


def test_safe_id_rejects_non_string():
    with pytest.raises(ContractError):
        safe_id(123, "x")


# ---------------------------------------------------------------------------
# now_ts / parse_ts
# ---------------------------------------------------------------------------

def test_now_ts_parses():
    ts = now_ts()
    parsed = parse_ts(ts, "ts")
    assert parsed.tzinfo is not None


def test_parse_ts_rejects_bad():
    with pytest.raises(ContractError):
        parse_ts("2024-01-01", "ts")


# ---------------------------------------------------------------------------
# exact_keys
# ---------------------------------------------------------------------------

def test_exact_keys_ok():
    d = exact_keys({"a": 1, "b": 2}, ["a", "b"])
    assert d["a"] == 1


def test_exact_keys_missing():
    with pytest.raises(ContractError):
        exact_keys({"a": 1}, ["a", "b"])


def test_exact_keys_extra():
    with pytest.raises(ContractError):
        exact_keys({"a": 1, "c": 3}, ["a"])


def test_exact_keys_optional_ok():
    exact_keys({"a": 1, "opt": 2}, ["a"], optional=["opt"])


# ---------------------------------------------------------------------------
# canonical_json
# ---------------------------------------------------------------------------

def test_canonical_json_deterministic():
    a = canonical_json({"z": 1, "a": 2})
    b = canonical_json({"a": 2, "z": 1})
    assert a == b


def test_canonical_json_rejects_float():
    with pytest.raises(ContractError):
        canonical_json({"x": 1.5})


def test_canonical_json_rejects_int_key():
    with pytest.raises(ContractError):
        canonical_json({1: "a"})


def test_canonical_json_rejects_none_value_not_really():
    # None IS allowed in canonical_json (it serialises as null)
    b = canonical_json({"x": None})
    assert b == b'{"x":null}'


# ---------------------------------------------------------------------------
# fingerprint
# ---------------------------------------------------------------------------

def test_fingerprint_deterministic():
    a = fingerprint({"k": 1}, "domain/v1")
    b = fingerprint({"k": 1}, "domain/v1")
    assert a == b


def test_fingerprint_domain_sensitive():
    a = fingerprint({"k": 1}, "domain-a/v1")
    b = fingerprint({"k": 1}, "domain-b/v1")
    assert a != b


def test_fingerprint_starts_sha256():
    fp = fingerprint({"x": 1}, "test/v1")
    assert fp.startswith("sha256:")


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

def test_gate_decision_values():
    assert GateDecision.ALLOWED.value == "allowed"
    assert GateDecision.BLOCKED.value == "blocked"
    assert GateDecision.ASK_USER.value == "ask_user"


def test_verification_status_values():
    assert VerificationStatus.PASSED.value == "passed"
    assert VerificationStatus.FAILED.value == "failed"
    assert VerificationStatus.UNAVAILABLE.value == "unavailable"
