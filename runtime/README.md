# runtime/

In-flight, run-generated state - not source. Gitignored by default
(see ../.gitignore) except for `.gitkeep` placeholders.

- `execution/` - per-run subprocess bookkeeping (src/harness/execution/process.py)
- `state/`     - run state machine + budget snapshots (src/harness/orchestration/state.py)
- `sessions/`  - per-session records
- `workspace/` - before/after workspace snapshots (src/harness/workspace/snapshot.py)
- `lifecycle/` - start/stop/teardown bookkeeping for long-running sessions
