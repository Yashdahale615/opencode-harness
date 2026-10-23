# Security

`src/harness/` implements the permission, verification and gating logic
that stands between an untrusted coding agent and the workspace it is
allowed to mutate. Treat any change to `permission/`, `gate/`,
`evidence/`, or `verification/` as security-sensitive.

## Status

This is a design reference and working skeleton, **not** a hardened,
production-ready security boundary. Pair it with your own threat model
before relying on it to sandbox an untrusted agent. See `docs/security.md`
and Section 17 of `docs/verified_execution_harness.pdf` for the security
model this skeleton implements and its known edges (e.g. symlink/TOCTOU
handling in `workspace/paths.py`, trust-ancestry checks in
`verification/catalog.py`).

## Reporting a vulnerability

Please open a private security advisory on this repository rather than a
public issue. Include reproduction steps; `tests/security/` is a good
reference for the kind of adversarial scenario this harness is meant to
reject.
