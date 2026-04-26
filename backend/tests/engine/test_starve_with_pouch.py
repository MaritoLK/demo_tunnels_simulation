"""Survival rung: agent with food in pouch must eat it before starving.

Pre-fix behaviour (caught by the 1700-tick diagnostic on 2026-04-26):
17/20 agents starved while carrying full cargo of food. The eat_cargo
rung was rogue-only, so non-rogues stranded in the field with hunger
at 0 and 8 units of food in their pouch died holding food. Survival
must outrank resource conservation — the colony loses more from a
dead agent than from a 1-unit pouch debit.
"""
from app.engine import needs
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


def _colony():
    return EngineColony(
        id=1, name='Red', color='#e74c3c',
        camp_x=0, camp_y=0, food_stock=0,
    )


def test_non_rogue_hunger_crit_with_pouch_eats_cargo():
    # Hungry non-rogue, far from camp, no food adjacent, cargo > 0.
    # Must pick eat_cargo, not forage (which would BFS for nothing
    # and fall to explore → starvation).
    world = _grass()
    colony = _colony()
    a = Agent(name='A', x=5, y=5, agent_id=1, colony_id=1)
    a.hunger = 5.0  # below HUNGER_CRITICAL (20)
    a.cargo_food = 3.0
    decision = decide_action(a, world, colony, 'day')
    assert decision.action == 'eat_cargo', (
        f'expected eat_cargo when hunger crit + cargo > 0, got '
        f'{decision.action!r} ({decision.reason!r})'
    )


def test_health_crit_with_pouch_eats_cargo_for_recovery():
    # Health critical, energy fine, cargo > 0. Pre-fix the rung sent
    # the agent to forage to recover; if no food was reachable they
    # starved holding food. Now must eat from pouch.
    world = _grass()
    colony = _colony()
    a = Agent(name='A', x=5, y=5, agent_id=1, colony_id=1)
    a.health = 10.0  # below HEALTH_CRITICAL
    a.energy = 80.0
    a.hunger = 30.0  # above critical so the hunger rung doesn't fire first
    a.cargo_food = 2.0
    decision = decide_action(a, world, colony, 'day')
    assert decision.action == 'eat_cargo', (
        f'expected eat_cargo when health crit + cargo > 0, got '
        f'{decision.action!r} ({decision.reason!r})'
    )


def test_health_crit_no_cargo_still_forages():
    # Cargo empty: must fall back to forage as before (no regression).
    world = _grass()
    colony = _colony()
    a = Agent(name='A', x=5, y=5, agent_id=1, colony_id=1)
    a.health = 10.0
    a.energy = 80.0
    a.hunger = 30.0
    a.cargo_food = 0.0
    decision = decide_action(a, world, colony, 'day')
    assert decision.action == 'forage', (
        f'cargo-empty health-crit must forage, got {decision.action!r}'
    )


def test_hunger_crit_no_cargo_still_forages():
    world = _grass()
    colony = _colony()
    a = Agent(name='A', x=5, y=5, agent_id=1, colony_id=1)
    a.hunger = 5.0
    a.cargo_food = 0.0
    decision = decide_action(a, world, colony, 'day')
    assert decision.action == 'forage', (
        f'cargo-empty hunger-crit must forage, got {decision.action!r}'
    )


def test_health_crit_energy_crit_still_rests():
    # The "rest first when both are critical" branch must keep
    # priority over the new pouch-eat rung — sleeping cures the
    # energy collapse while eating won't.
    world = _grass()
    colony = _colony()
    a = Agent(name='A', x=5, y=5, agent_id=1, colony_id=1)
    a.health = 10.0
    a.energy = 10.0
    a.cargo_food = 5.0
    decision = decide_action(a, world, colony, 'day')
    assert decision.action == 'rest', (
        f'expected rest when health+energy both critical, got '
        f'{decision.action!r}'
    )
