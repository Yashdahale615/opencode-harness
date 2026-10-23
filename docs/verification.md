# Verification

Independent, pre-registered checks - not the agent grading its own work.
`verification/catalog.py` loads a trusted catalog (hash-pinned, ancestry
validated), `verification/select.py` picks the checks whose `scope`
globs cover the paths that actually changed, and `verification/runtime.py`
runs them and aggregates the result into `PASSED` / `FAILED` /
`UNAVAILABLE`. `gate/reconcile.py` then confirms the workspace didn't
change again while verification was running before the gate
(`gate/decision.py`) will accept it.
