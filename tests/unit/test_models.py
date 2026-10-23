"""Unit tests for harness.models.route."""
import pytest
from harness.models.route import Profile, TaskFeatures, route


def make_profiles():
    return {
        "core": Profile("core", "gemini-1.5-flash", 100_000, 10, 1),
        "deep": Profile("deep", "gemini-1.5-pro",  200_000, 50, 2),
        "orchestration": Profile("orchestration", "gemini-1.5-pro", 100_000, 30, 2),
    }


def t(**kwargs):
    defaults = dict(
        complexity=1, risk=0, context_tokens=1000,
        needs_planning=False, remaining_cost_micro_usd=10_000_000,
    )
    defaults.update(kwargs)
    return TaskFeatures(**defaults)


def test_simple_task_routes_core():
    p = route(make_profiles(), t(complexity=0, risk=0))
    assert p.name == "core"


def test_complex_routes_deep():
    p = route(make_profiles(), t(complexity=2, risk=0))
    assert p.name == "deep"


def test_high_risk_routes_deep():
    p = route(make_profiles(), t(complexity=0, risk=2))
    assert p.name == "deep"


def test_planning_routes_orchestration():
    p = route(make_profiles(), t(needs_planning=True))
    assert p.name == "orchestration"


def test_context_too_large_raises():
    with pytest.raises(ValueError, match="context"):
        route(make_profiles(), t(context_tokens=999_999))


def test_budget_degrades_to_core():
    # Deep is too expensive with very large context; core is cheaper and fits
    profs = {
        "core": Profile("core", "gemini-1.5-flash", 200_000, 1, 1),
        "deep": Profile("deep", "gemini-1.5-pro",  200_000, 50, 2),
        "orchestration": Profile("orchestration", "gemini-1.5-pro", 100_000, 30, 2),
    }
    # remaining_cost_micro_usd=100: deep costs 50*(1000//1000+1)=100, core costs 1*2=2
    # So deep estimate (100) == remaining, but core (2) < remaining
    # Actually: est = cost_per_1k * (tokens//1000 + 1)
    # deep: 50*(1000//1000+1) = 50*2 = 100, remaining=100 -> NOT > remaining, so deep wins
    # We need deep to be MORE expensive than remaining
    p = route(profs, t(complexity=2, risk=0, context_tokens=1000, remaining_cost_micro_usd=50))
    assert p.name == "core"


def test_no_affordable_profile_raises():
    # Even core is too expensive
    profs = {"core": Profile("core", "m", 100_000, 10_000_000, 1)}
    with pytest.raises(ValueError):
        route(profs, t(complexity=0, risk=0, remaining_cost_micro_usd=1))
