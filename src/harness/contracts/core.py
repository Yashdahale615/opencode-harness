"""harness/contracts/core.py - trust foundation. Standard library only."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from enum import Enum


class ContractError(ValueError):
    """Raised for ANY malformed, unknown or unsafe contract data."""


SCHEMA_VERSIONS = {"trace": 1, "report": 1, "decision": 1,
                   "policy": 1, "receipt": 1, "catalog": 1}


class GateDecision(str, Enum):
    ALLOWED = "allowed"
    BLOCKED = "blocked"
    ASK_USER = "ask_user"


class VerificationStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"


class Verdict(str, Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


_SAFE_ID = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9_-]{0,62}[A-Za-z0-9])?")
_TS = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z")


def safe_id(value: object, field: str) -> str:
    """IDs become file names and log keys: no dots, slashes or spaces."""
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise ContractError(f"{field}: unsafe identifier")
    return value


def parse_ts(value: object, field: str) -> datetime:
    if not isinstance(value, str) or not _TS.fullmatch(value):
        raise ContractError(f"{field}: expected RFC 3339 UTC, e.g. ...Z")
    fmt = "%Y-%m-%dT%H:%M:%S.%fZ" if "." in value else "%Y-%m-%dT%H:%M:%SZ"
    return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)


def now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def exact_keys(obj: object, required, optional=(), where="object") -> dict:
    """Reject missing AND unknown keys. Unknown keys are attack surface."""
    if not isinstance(obj, dict):
        raise ContractError(f"{where}: expected an object")
    keys, req = set(obj), set(required)
    missing, extra = req - keys, keys - (req | set(optional))
    if missing or extra:
        raise ContractError(
            f"{where}: missing={sorted(missing)} unknown={sorted(extra)}")
    return obj


def enum_of(cls, value: object, field: str):
    try:
        return cls(value)
    except ValueError:
        raise ContractError(f"{field}: invalid value {value!r}") from None


def _check_json(o: object) -> None:
    if isinstance(o, float):
        raise ContractError("floats are forbidden in fingerprinted data")
    if isinstance(o, dict):
        for k, v in o.items():
            if not isinstance(k, str):
                raise ContractError("object keys must be strings")
            _check_json(v)
    elif isinstance(o, (list, tuple)):
        for v in o:
            _check_json(v)
    elif o is not None and not isinstance(o, (str, int, bool)):
        raise ContractError(f"unsupported type {type(o).__name__}")


def canonical_json(obj: object) -> bytes:
    _check_json(obj)
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def fingerprint(obj: object, domain: str) -> str:
    """SHA-256 over domain + NUL + canonical JSON (domain separation)."""
    h = hashlib.sha256()
    h.update(domain.encode("ascii") + b"\x00")
    h.update(canonical_json(obj))
    return "sha256:" + h.hexdigest()
