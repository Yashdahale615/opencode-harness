# Execution

Tool calls that pass permission (`src/harness/permission`) run through
`src/harness/execution/process.py`: contained subprocess execution with
timeouts and process-group teardown. `tests/security/test_more.py`
exercises this directly - timeouts, nonexistent executables, executables
planted inside the workspace (rejected), and exit-code propagation.
