"""harness/gate/reconcile.py - did verification itself change the world?"""
from __future__ import annotations

from dataclasses import dataclass

from harness.workspace.snapshot import Entry, diff, workspace_fingerprint


@dataclass(frozen=True)
class Reconciliation:
    unchanged: bool
    changed_paths: tuple[str, ...]
    mutation_revision: int
    workspace_fp: str


def reconcile(pre_check: dict[str, Entry], post_check: dict[str, Entry],
              mutation_revision: int) -> Reconciliation:
    d = diff(pre_check, post_check)
    rev = mutation_revision if not d else mutation_revision + 1
    return Reconciliation(not d, d.changed, rev,
                          workspace_fingerprint(post_check))
