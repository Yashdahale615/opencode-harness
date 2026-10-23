"""harness/observability/trace.py - append-only, hash-chained trace."""
from __future__ import annotations

import json
import os
from pathlib import Path

from harness.contracts.core import (ContractError, canonical_json, fingerprint,
                                    now_ts, safe_id)

GENESIS = "sha256:" + "0" * 64


class TraceWriter:
    def __init__(self, path: Path, job_id: str) -> None:
        self.job_id = safe_id(job_id, "job_id")
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        self._fd = os.open(path, flags, 0o600)
        self._prev, self._seq = GENESIS, 0

    def emit(self, kind: str, data: dict) -> str:
        ev = {"schema": 1, "job_id": self.job_id, "seq": self._seq,
              "ts": now_ts(), "kind": safe_id(kind, "kind"),
              "data": data, "prev": self._prev}
        ev["hash"] = fingerprint(ev, "trace-event/v1")   # computed w/o "hash"
        os.write(self._fd, canonical_json(ev) + b"\n")
        os.fsync(self._fd)                               # durable before use
        self._prev, self._seq = ev["hash"], self._seq + 1
        return ev["hash"]

    def close(self) -> None:
        os.close(self._fd)


def verify_chain(path: Path) -> int:
    """Return number of valid events or raise ContractError at first break."""
    prev, n = GENESIS, 0
    for line in path.read_bytes().splitlines():
        ev = json.loads(line)
        claimed = ev.pop("hash", None)
        if ev.get("prev") != prev or ev.get("seq") != n:
            raise ContractError(f"trace broken at seq {n}")
        if fingerprint(ev, "trace-event/v1") != claimed:
            raise ContractError(f"trace tampered at seq {n}")
        prev, n = claimed, n + 1
    return n
