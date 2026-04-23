"""Decision is a frozen, slotted dataclass with action + reason fields.
These tests lock the shape — callers will rely on both attributes existing."""
import pytest

from app.engine.agent import Decision


def test_decision_has_action_and_reason():
    d = Decision('rest', 'health < 20, energy < 15 → rest')
    assert d.action == 'rest'
    assert d.reason == 'health < 20, energy < 15 → rest'


def test_decision_is_frozen():
    d = Decision('rest', 'r')
    with pytest.raises(Exception):  # FrozenInstanceError is a dataclass error
        d.action = 'forage'


def test_decision_uses_slots():
    d = Decision('rest', 'r')
    with pytest.raises((AttributeError, TypeError)):  # slots=True → no __dict__
        d.extra = 'whatever'
