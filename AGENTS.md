# AGENTS.md

Instructions for coding agents (including OpenCode-based agents) working
in this repository.

## What this repo is

A verified-execution harness: every tool call an agent makes is
permission-checked (`src/harness/permission`), every mutation is
snapshotted (`src/harness/workspace`), and nothing is reported as
successful until an independent, pre-registered check has verified it
(`src/harness/verification`) and the gate has made a single, evidence-based
decision (`src/harness/gate`, `src/harness/evidence`).

## Rules for agents editing this repo

1. **Keep `src/harness/gate/decision.py` pure.** `decide()` must remain a
   function of its `GateInput` only - no I/O, no clock, no randomness.
2. **Don't weaken default-deny.** `permission/policy.py: evaluate()` must
   keep returning `DENY` when no rule matches.
3. **Don't bypass trust-ancestry checks** in `verification/catalog.py`
   (`assert_trusted_ancestry`) - these exist specifically to stop an agent
   from supplying its own "trusted" check catalog.
4. **Run the tests before finishing a change**:
   ```bash
   python3 tests/unit/test_all.py
   python3 tests/security/test_more.py
   ```
5. Read `docs/security.md` and `SECURITY.md` before touching anything
   under `src/harness/permission/`, `gate/`, `evidence/`, or
   `verification/`.

See `profiles/` for the acceptance-policy presets (`safe`, `default`,
`autonomous`, `benchmark`) an agent may be run under.
