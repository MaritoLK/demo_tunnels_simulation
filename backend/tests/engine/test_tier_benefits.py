"""Tier benefits: cargo cap, movement speed, rest energy, eat cost,
pop cap all scale with `colony.tier`. The user wants these to "match
the difficulty to get there" — tier 1 (Monastery, 15w/8s) and tier 2
(Castle, 40w/25s) each unlock a meaningful step.
"""
import random

from app.engine import actions, config, needs
from app.engine.agent import Agent, decide_action
from app.engine.colony import EngineColony
from app.engine.world import Tile, World


def _grass(width=10, height=10):
    w = World(width, height)
    w.tiles = [
        [Tile(x, y, 'grass') for x in range(width)]
        for y in range(height)
    ]
    return w


def _colony(tier=0):
    return EngineColony(
        id=1, name='Red', color='#e74c3c',
        camp_x=0, camp_y=0, food_stock=0, tier=tier,
    )


# ---- carry_max -----------------------------------------------------------


def test_carry_max_scales_with_tier():
    assert needs.carry_max_for(_colony(tier=0)) == 8
    assert needs.carry_max_for(_colony(tier=1)) == 12
    assert needs.carry_max_for(_colony(tier=2)) == 16


def test_carry_max_handles_no_colony():
    # Synthesized agents in unit tests pass colony=None — fall back
    # to tier 0 baseline so legacy tests keep working.
    assert needs.carry_max_for(None) == 8


def test_decide_action_uses_tier_aware_cap():
    # Agent at a tier-2 colony has CARRY_MAX 16. With cargo weight 14
    # (7 wood) the agent is NOT full and should keep doing field work.
    world = _grass()
    colony = _colony(tier=2)
    a = Agent(name='A', x=5, y=5, agent_id=1, colony_id=1)
    a.cargo_wood = 7.0  # 7 * 2 = 14 weight, below 16 cap
    a.hunger = 80.0
    a.energy = 80.0
    a.social = 80.0
    decision = decide_action(a, world, colony, 'day')
    assert decision.action != 'step_to_camp', (
        f'tier-2 cap is 16, weight 14 should not force home: {decision.reason!r}'
    )


# ---- rest energy ---------------------------------------------------------


def test_rest_energy_scales_with_tier():
    a_t0 = Agent(name='A', x=0, y=0, agent_id=1, colony_id=1)
    a_t0.energy = 50.0
    actions.rest(a_t0, _colony(tier=0))
    assert a_t0.energy == 55.0  # +5

    a_t1 = Agent(name='B', x=0, y=0, agent_id=2, colony_id=1)
    a_t1.energy = 50.0
    actions.rest(a_t1, _colony(tier=1))
    assert a_t1.energy == 58.0  # +8

    a_t2 = Agent(name='C', x=0, y=0, agent_id=3, colony_id=1)
    a_t2.energy = 50.0
    actions.rest(a_t2, _colony(tier=2))
    assert a_t2.energy == 62.0  # +12


# ---- eat cost ------------------------------------------------------------


def test_eat_cost_scales_with_tier():
    for tier, expected_cost in [(0, 6), (1, 5), (2, 4)]:
        colony = _colony(tier=tier)
        colony.food_stock = 100
        a = Agent(name='A', x=0, y=0, agent_id=1, colony_id=1)
        a.hunger = 30.0
        actions.eat_camp(a, colony)
        assert colony.food_stock == 100 - expected_cost, (
            f'tier {tier} eat_cost expected {expected_cost}, '
            f'got {100 - colony.food_stock}'
        )


# ---- movement reduction --------------------------------------------------


def test_move_cost_drops_with_tier():
    forest = Tile(0, 0, 'forest', resource_type='wood', resource_amount=5.0)
    stone = Tile(0, 0, 'stone', resource_type='stone', resource_amount=5.0)
    # Tier 0: forest = 2, stone = 3.
    assert actions.move_cost(forest, _colony(tier=0)) == 2
    assert actions.move_cost(stone, _colony(tier=0)) == 3
    # Tier 1: -1 reduction (clamped at 1).
    assert actions.move_cost(forest, _colony(tier=1)) == 1
    assert actions.move_cost(stone, _colony(tier=1)) == 2
    # Tier 2: -2 reduction.
    assert actions.move_cost(forest, _colony(tier=2)) == 1
    assert actions.move_cost(stone, _colony(tier=2)) == 1


# ---- pop cap -------------------------------------------------------------


def test_pop_cap_scales_with_tier():
    assert config.tier_benefit(_colony(tier=0), 'pop_cap') == 8
    assert config.tier_benefit(_colony(tier=1), 'pop_cap') == 12
    assert config.tier_benefit(_colony(tier=2), 'pop_cap') == 16
