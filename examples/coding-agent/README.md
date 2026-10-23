# coding-agent

Intended to show a full session: an agent edits files, the harness
snapshots the workspace (src/harness/workspace/snapshot.py), runs the
trusted checks that cover what changed (src/harness/verification), and the
gate (src/harness/gate/decision.py) either accepts, blocks, reverifies, or
asks the user. Not implemented yet - see tests/unit/test_all.py for the
individual pieces exercised end to end without a real agent in the loop.
