"""Unit tests for harness.orchestration.state."""
import pytest
from harness.orchestration.state import (
    Budget,
    BudgetExceeded,
    IllegalTransition,
    RunMachine,
    RunState,
)

S = RunState


def test_initial_state():
    m = RunMachine()
    assert m.state == S.CREATED


def test_legal_transitions():
    m = RunMachine()
    m.go(S.CONTEXT_READY)
    m.go(S.PLANNED)
    m.go(S.EXECUTING)
    m.go(S.VERIFYING)
    m.go(S.GATING)
    m.go(S.TERMINAL_VERIFIED)
    assert m.state == S.TERMINAL_VERIFIED


def test_illegal_transition():
    m = RunMachine()
    m.go(S.CONTEXT_READY)
    with pytest.raises(IllegalTransition):
        m.go(S.TERMINAL_VERIFIED)


def test_history_recorded():
    m = RunMachine()
    m.go(S.CONTEXT_READY)
    assert (S.CREATED, S.CONTEXT_READY) in m.history


def test_gating_can_go_back_to_verifying():
    m = RunMachine()
    m.go(S.CONTEXT_READY)
    m.go(S.PLANNED)
    m.go(S.EXECUTING)
    m.go(S.VERIFYING)
    m.go(S.GATING)
    m.go(S.VERIFYING)   # allowed (reverify loop)
    assert m.state == S.VERIFYING


def test_budget_token_exceeded():
    b = Budget(max_tokens=100, max_cost_micro_usd=99999, max_attempts=5)
    with pytest.raises(BudgetExceeded):
        b.charge(tokens=200)


def test_budget_cost_exceeded():
    b = Budget(max_tokens=99999, max_cost_micro_usd=100, max_attempts=5)
    with pytest.raises(BudgetExceeded):
        b.charge(cost_micro_usd=200)


def test_budget_attempts_exceeded():
    b = Budget(max_tokens=99999, max_cost_micro_usd=99999, max_attempts=2)
    b.start_attempt()
    b.start_attempt()
    with pytest.raises(BudgetExceeded):
        b.start_attempt()


def test_budget_charge_accumulates():
    b = Budget(max_tokens=1000, max_cost_micro_usd=9999, max_attempts=5)
    b.charge(tokens=400)
    b.charge(tokens=400)
    # 800 <= 1000, no error
    assert b.tokens == 800
