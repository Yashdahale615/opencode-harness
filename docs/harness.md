# The harness package

`src/harness/` is organized by concern:

| Module                        | Responsibility |
|--------------------------------|----------------|
| `contracts/core.py`            | safe IDs, timestamps, canonical JSON, fingerprints |
| `context/select.py`            | budgeted context selection |
| `models/route.py`              | model/profile routing |
| `orchestration/state.py`       | run state machine + budget |
| `permission/policy.py`         | risk classification, rule evaluation |
| `execution/process.py`         | contained subprocess execution |
| `workspace/paths.py`           | symlink + TOCTOU-safe path handling |
| `workspace/snapshot.py`        | before/after snapshot, diff, fingerprint |
| `verification/catalog.py`      | trusted catalog loading + identity validation |
| `verification/select.py`       | scope/cost based check selection |
| `verification/runtime.py`      | run checks, aggregate PASSED/FAILED/UNAVAILABLE |
| `gate/decision.py`             | the pure gate decision function |
| `gate/reconcile.py`            | post-verification reconciliation |
| `observability/trace.py`       | hash-chained append-only trace |
| `evidence/receipt.py`          | Evidence, build_receipt, verify_receipt |

`entry.py`, `controller.py`, `policy.py`, `executor.py`, `verifier.py`,
`receipt.py`, and `fingerprint.py` at the top of `src/harness/` are thin
re-export shims over the packages above, for shorter import paths.
