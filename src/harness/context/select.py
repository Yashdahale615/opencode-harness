"""harness/context/select.py - budgeted context selection + fingerprint."""
from __future__ import annotations

from dataclasses import dataclass

from harness.contracts.core import ContractError, fingerprint


@dataclass(frozen=True)
class ContextItem:
    key: str                 # e.g. "file:src/a.py", "git:diff", "task"
    text: str
    priority: int            # 0 = mandatory, higher number = less important
    tokens: int              # pre-computed estimate (integer)


def select_context(items: list[ContextItem], budget_tokens: int,
                   compress=None):
    """Mandatory items first, then by priority. compress(item, room) may
    return a smaller ContextItem (summary) or None to drop the item."""
    chosen, used = [], 0
    ordered = sorted(items, key=lambda i: (i.priority, i.tokens, i.key))
    for it in ordered:
        room = budget_tokens - used
        if it.tokens > room:
            if it.priority == 0:
                raise ContractError(f"mandatory context {it.key} > budget")
            it = compress(it, room) if compress else None
            if it is None or it.tokens > room:
                continue
        chosen.append(it)
        used += it.tokens
    fp = fingerprint([[i.key, fingerprint(i.text, "ctx-item/v1")]
                      for i in chosen], "context/v1")
    return chosen, used, fp
