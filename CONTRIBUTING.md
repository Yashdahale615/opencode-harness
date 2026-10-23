# Contributing

This repository is a design reference and working skeleton for a
verified-execution harness, not (yet) a hardened production system - see
`README.md` and `docs/security.md` for the current status and known edges.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Running the tests

```bash
python3 tests/unit/test_all.py
python3 tests/security/test_more.py
# or, once test files are converted to real pytest cases:
pytest
```

`tests/unit` and `tests/security` currently run real filesystem and process
operations and print `ok: ...` for each expected rejection rather than using
an assertion framework - see each file's module docstring before adapting it.

## Code layout

All harness logic lives in `src/harness/`, organized by concern
(`permission`, `execution`, `workspace`, `verification`, `gate`,
`evidence`, `observability`, `orchestration`, `contracts`, `context`,
`models`). The top-level `entry.py`, `controller.py`, `policy.py`,
`executor.py`, `verifier.py`, `receipt.py`, and `fingerprint.py` modules
are thin re-export shims over those packages, kept for shorter import
paths - see each shim's docstring for what it forwards.

## Pull requests

- Keep the gate decision function (`src/harness/gate/decision.py`) pure -
  no I/O, no clock reads, no randomness.
- Changes touching `permission/`, `gate/`, `evidence/`, or `verification/`
  require review from `@opencode-harness/security` (see `CODEOWNERS`).
- Add or update a test alongside any behavioral change.
