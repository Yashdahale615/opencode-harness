"""harness/orchestration/state.py - explicit run state machine + budget."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class RunState(str, Enum):
    CREATED = "created"
    CONTEXT_READY = "context_ready"
    PLANNED = "planned"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    GATING = "gating"
    TERMINAL_VERIFIED = "terminal_verified"
    TERMINAL_BLOCKED = "terminal_blocked"
    TERMINAL_FAILED = "terminal_failed"


S = RunState
_ALLOWED = {
    S.CREATED: {S.CONTEXT_READY, S.TERMINAL_FAILED},
    S.CONTEXT_READY: {S.PLANNED, S.TERMINAL_FAILED},
    S.PLANNED: {S.EXECUTING, S.TERMINAL_FAILED},
    S.EXECUTING: {S.VERIFYING, S.GATING, S.TERMINAL_FAILED},
    S.VERIFYING: {S.GATING, S.TERMINAL_FAILED},
    S.GATING: {S.VERIFYING, S.EXECUTING, S.TERMINAL_VERIFIED,
               S.TERMINAL_BLOCKED, S.TERMINAL_FAILED},
}


class IllegalTransition(RuntimeError):
    pass


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class Budget:
    max_tokens: int
    max_cost_micro_usd: int
    max_attempts: int
    tokens: int = 0
    cost_micro_usd: int = 0
    attempts: int = 0

    def charge(self, tokens: int = 0, cost_micro_usd: int = 0) -> None:
        self.tokens += tokens
        self.cost_micro_usd += cost_micro_usd
        if (self.tokens > self.max_tokens
                or self.cost_micro_usd > self.max_cost_micro_usd):
            raise BudgetExceeded("token or cost budget exhausted")

    def start_attempt(self) -> None:
        self.attempts += 1
        if self.attempts > self.max_attempts:
            raise BudgetExceeded("retry budget exhausted")


@dataclass
class RunMachine:
    state: RunState = RunState.CREATED
    history: list[tuple[RunState, RunState]] = field(default_factory=list)

    def go(self, nxt: RunState) -> None:
        if nxt not in _ALLOWED.get(self.state, set()):
            raise IllegalTransition(f"{self.state.value} -> {nxt.value}")
        self.history.append((self.state, nxt))
        self.state = nxt
