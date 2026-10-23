"""Unit tests for harness.observability.trace."""
import json
import tempfile
from pathlib import Path

import pytest
from harness.contracts.core import ContractError
from harness.observability.trace import TraceWriter, verify_chain


def fresh_trace(job_id="job-1"):
    tmp = Path(tempfile.mkdtemp())
    path = tmp / "trace.jsonl"
    return path, TraceWriter(path, job_id)


def test_emit_and_verify():
    path, tw = fresh_trace()
    tw.emit("start", {"a": 1})
    tw.emit("end",   {"b": 2})
    tw.close()
    n = verify_chain(path)
    assert n == 2


def test_empty_chain():
    path, tw = fresh_trace()
    tw.close()
    assert verify_chain(path) == 0


def test_tamper_detected():
    path, tw = fresh_trace()
    tw.emit("event", {"x": 1})
    tw.close()
    lines = path.read_bytes().splitlines()
    ev = json.loads(lines[0])
    ev["data"]["x"] = 999
    path.write_bytes(json.dumps(ev).encode() + b"\n")
    with pytest.raises(ContractError):
        verify_chain(path)


def test_seq_broken():
    path, tw = fresh_trace()
    tw.emit("e1", {"x": 1})
    tw.emit("e2", {"x": 2})
    tw.close()
    lines = path.read_bytes().splitlines()
    # Remove first line -> seq starts at 1, not 0
    path.write_bytes(lines[1] + b"\n")
    with pytest.raises(ContractError):
        verify_chain(path)


def test_hash_chaining():
    """Each event's prev field must equal the hash of the prior event."""
    path, tw = fresh_trace()
    h1 = tw.emit("a", {})
    h2 = tw.emit("b", {})
    tw.close()
    lines = path.read_bytes().splitlines()
    e1 = json.loads(lines[0])
    e2 = json.loads(lines[1])
    assert e1["hash"] == h1
    assert e2["prev"] == h1
    assert e2["hash"] == h2
