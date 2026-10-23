"""Unit tests for harness.context.select."""
import pytest
from harness.context.select import ContextItem, select_context
from harness.contracts.core import ContractError


def item(key, priority, tokens):
    return ContextItem(key=key, text=f"text-{key}", priority=priority, tokens=tokens)


def test_select_fits_all():
    items = [item("a", 0, 100), item("b", 1, 200)]
    chosen, used, fp = select_context(items, 500)
    assert len(chosen) == 2
    assert used == 300
    assert fp.startswith("sha256:")


def test_mandatory_item_exceeds_budget():
    items = [item("big", 0, 9999)]
    with pytest.raises(ContractError, match="mandatory"):
        select_context(items, 100)


def test_low_priority_dropped_if_no_room():
    items = [item("required", 0, 100), item("optional", 1, 9999)]
    chosen, used, _ = select_context(items, 200)
    keys = [i.key for i in chosen]
    assert "required" in keys
    assert "optional" not in keys


def test_fingerprint_stable():
    items = [item("a", 0, 50)]
    _, _, fp1 = select_context(items, 100)
    _, _, fp2 = select_context(items, 100)
    assert fp1 == fp2


def test_fingerprint_changes_when_items_differ():
    items1 = [item("a", 0, 50)]
    items2 = [item("b", 0, 50)]
    _, _, fp1 = select_context(items1, 100)
    _, _, fp2 = select_context(items2, 100)
    assert fp1 != fp2


def test_ordering_by_priority():
    items = [item("low", 2, 50), item("high", 0, 50), item("med", 1, 50)]
    chosen, _, _ = select_context(items, 200)
    priorities = [c.priority for c in chosen]
    assert priorities == sorted(priorities)


def test_compress_callback():
    big = ContextItem(key="big", text="x" * 1000, priority=1, tokens=800)
    small = ContextItem(key="big", text="x" * 100, priority=1, tokens=80)

    def compress(it, room):
        if room >= 80:
            return small
        return None

    mandatory = ContextItem(key="m", text="m", priority=0, tokens=100)
    chosen, used, _ = select_context([mandatory, big], 250, compress=compress)
    keys = [i.key for i in chosen]
    assert "m" in keys
    assert "big" in keys    # compressed version should fit
