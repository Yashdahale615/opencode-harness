# Security model

See the top-level `SECURITY.md` for status and vulnerability reporting.

Threats this skeleton addresses in `src/harness/`:
- **Default-deny permissioning** (`permission/policy.py`): no matching
  rule -> `DENY`.
- **Symlink / TOCTOU-safe workspace paths** (`workspace/paths.py`).
- **Trusted-check identity validation** (`verification/catalog.py`):
  checks are hash-pinned and their ancestry validated so an agent cannot
  supply its own catalog.
- **Tamper-evident trace** (`observability/trace.py`): hash-chained,
  append-only; `tests/security/test_more.py` demonstrates tampering being
  detected.
- **Signed, workspace-bound receipts** (`evidence/receipt.py`): a receipt
  that doesn't match the current workspace fingerprint, or whose body was
  altered, fails `verify_receipt`.

Full threat model and known edges: Section 17 of
`verified_execution_harness.pdf`.
