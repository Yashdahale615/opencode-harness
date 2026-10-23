"""Security tests: trace chain integrity and tamper detection."""
import json
import tempfile
from pathlib import Path

import pytest
from harness.contracts.core import ContractError
from harness.observability.trace import TraceWriter, verify_chain


def make_trace(*events):
    tmp = Path(tempfile.mkdtemp())
    path = tmp / "trace.jsonl"
    tw = TraceWriter(path, "job-sec")
    for kind, data in events:
        tw.emit(kind, data)
    tw.close()
    return path


def test_single_event_chain_ok():
    path = make_trace(("start", {"x": 1}))
    assert verify_chain(path) == 1


def test_multi_event_chain_ok():
    path = make_trace(("a", {}), ("b", {}), ("c", {}))
    assert verify_chain(path) == 3


def test_tamper_first_event():
    path = make_trace(("start", {"x": 1}), ("end", {"y": 2}))
    lines = path.read_bytes().splitlines()
    ev = json.loads(lines[0])
    ev["data"]["x"] = 999
    path.write_bytes(json.dumps(ev).encode() + b"\n" + lines[1] + b"\n")
    with pytest.raises(ContractError):
        verify_chain(path)


def test_tamper_second_event():
    path = make_trace(("a", {}), ("b", {"secret": "original"}))
    lines = path.read_bytes().splitlines()
    ev = json.loads(lines[1])
    ev["data"]["secret"] = "injected"
    path.write_bytes(lines[0] + b"\n" + json.dumps(ev).encode() + b"\n")
    with pytest.raises(ContractError):
        verify_chain(path)


def test_insert_event_breaks_chain():
    path = make_trace(("a", {}), ("b", {}))
    lines = path.read_bytes().splitlines()
    fake = json.dumps({"schema": 1, "job_id": "job-sec", "seq": 1,
                       "ts": "2024-01-01T00:00:00Z", "kind": "evil",
                       "data": {}, "prev": "sha256:" + "0"*64,
                       "hash": "sha256:" + "a"*64})
    path.write_bytes(lines[0] + b"\n" + fake.encode() + b"\n" + lines[1] + b"\n")
    with pytest.raises(ContractError):
        verify_chain(path)


def test_replay_event_breaks_chain():
    path = make_trace(("a", {}), ("b", {}))
    content = path.read_bytes()
    # Repeat the file — duplicate events break seq/prev checks
    path.write_bytes(content + content)
    with pytest.raises(ContractError):
        verify_chain(path)


def test_empty_trace_valid():
    tmp = Path(tempfile.mkdtemp())
    path = tmp / "empty.jsonl"
    path.write_bytes(b"")
    assert verify_chain(path) == 0
