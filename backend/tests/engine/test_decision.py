"""Decision is a frozen, slotted dataclass with action + reason fields.
These tests lock the shape — callers will rely on both attributes existing."""
from dataclasses import FrozenInstanceError

import pytest

from app.engine.agent import Decision


def test_decision_has_action_and_reason():
    d = Decision('rest', 'health < 20, energy < 15 → rest')
    assert d.action == 'rest'
    assert d.reason == 'health < 20, energy < 15 → rest'


def test_decision_is_frozen():
    d = Decision('rest', 'r')
    # Narrow to FrozenInstanceError so a future unrelated error
    # (NameError, AttributeError from a surprise __setattr__) doesn't
    # silently satisfy this test. The job here is to catch the case
    # where someone drops frozen=True.
    with pytest.raises(FrozenInstanceError):
        d.action = 'forage'


def test_decision_uses_slots():
    d = Decision('rest', 'r')
    # frozen=True + slots=True on CPython 3.11+ raises TypeError from
    # super().__setattr__. Plain slots (no frozen) raises AttributeError
    # for the same attempt. Accept either — both mean "slots=True worked,
    # no __dict__, no new attrs."
    with pytest.raises((AttributeError, TypeError)):
        d.extra = 'whatever'
