# Configuration

- **Acceptance policy / risk tolerance**: `../profiles/*.yaml`
  (`safe`, `default`, `autonomous`, `benchmark`), loaded into
  `harness.gate.decision.AcceptancePolicy`.
- **Permission rules**: see `Rule` / `ToolRequest` in
  `src/harness/permission/policy.py`; example rule sets belong in
  `../fixtures/policies/`.
- **Trusted verification catalog**: JSON, loaded by
  `src/harness/verification/catalog.py`; example catalogs belong in
  `../fixtures/test-data/`.
- **OpenCode-specific settings**: `../.opencode/`.
