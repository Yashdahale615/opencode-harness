"""harness/models/route.py - profile-based model routing."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Profile:
    name: str                 # "core" | "deep" | "orchestration"
    model: str
    max_context: int
    cost_micro_usd_per_1k: int
    risk_ceiling: int         # highest risk (0-2) it may handle unattended


@dataclass(frozen=True)
class TaskFeatures:
    complexity: int           # 0 trivial .. 3 architectural
    risk: int                 # 0 low .. 2 high
    context_tokens: int
    needs_planning: bool
    remaining_cost_micro_usd: int


def route(profiles: dict[str, Profile], t: TaskFeatures) -> Profile:
    if t.needs_planning and "orchestration" in profiles:
        want = "orchestration"
    elif t.complexity >= 2 or t.risk >= 2:
        want = "deep"
    else:
        want = "core"
    p = profiles[want]
    est = p.cost_micro_usd_per_1k * (t.context_tokens // 1000 + 1)
    if t.context_tokens > p.max_context:
        raise ValueError(f"context does not fit profile {p.name}")
    if est > t.remaining_cost_micro_usd:
        core = profiles["core"]          # degrade, never overspend silently
        if core.risk_ceiling < t.risk:
            raise ValueError("cheaper profile not allowed at this risk level")
        if core.cost_micro_usd_per_1k * (t.context_tokens // 1000 + 1) \
                > t.remaining_cost_micro_usd:
            raise ValueError("budget too small for any profile")
        return core
    return p
