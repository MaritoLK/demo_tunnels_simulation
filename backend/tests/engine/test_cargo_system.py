"""Foragers carry what they pick up; deposit at camp tops up colony stock.

Before this: forage() added hunger to the agent but the tile units went
nowhere — agents couldn't stockpile for the colony. Food tiles felt like
vending machines, not a shared resource.

After this: each forage also puts up to CARRY_MAX units into the agent's
cargo. Hunger still fills normally (simulates eating during the gather).
A new deposit action at camp drains cargo into colony.food_stock, so the
cultivation/scarcity loop is fed by foraging as well as harvesting.
"""
import random

from app.engine import actions, needs
from app.engine.agent import Agent, decide_action
from app.engine.colony import EngineColony
from app.engine.world import Tile, World


def _grass_world(w=4, h=4):
    world = World(w, h)
    world.tiles = [[Tile(x, y, 'grass') for x in range(w)] for y in range(h)]
    return world


def _food_tile(world, x, y, amount=10.0):
    t = world.get_tile(x, y)
    t.resource_type = 'food'
    t.resource_amount = amount
    return t


def _colony(cx=0, cy=0, food_stock=20):
    return EngineColony(1, 'R', '#000', camp_x=cx, camp_y=cy, food_stock=food_stock)


# ─── slot + default ───────────────────────────────────────────────────

def test_agent_has_cargo_slot_defaulting_zero():
    a = Agent('A', 0, 0, agent_id=1, colony_id=1)
    assert a.cargo == 0


def test_needs_module_exposes_carry_max():
    assert hasattr(needs, 'CARRY_MAX')
    assert needs.CARRY_MAX > 0


# ─── forage fills cargo ───────────────────────────────────────────────

def test_forage_puts_tile_units_into_cargo():
    a = Agent('A', 0, 0, agent_id=1, colony_id=1)
    a.hunger = 50.0
    w = _grass_world()
    tile = _food_tile(w, 0, 0, amount=10.0)
    actions.forage(a, w, rng=random.Random(0))
    assert a.cargo == needs.FORAGE_TILE_DEPLETION
    # Tile still shows the shared depletion (engine-side authority).
    assert tile.resource_amount == 10.0 - needs.FORAGE_TILE_DEPLETION


def test_forage_cargo_capped_at_carry_max():
    a = Agent('A', 0, 0, agent_id=1, colony_id=1)
    a.hunger = 50.0
    a.cargo = needs.CARRY_MAX - 1  # almost full pouch
    w = _grass_world()
    tile = _food_tile(w, 0, 0, amount=10.0)
    actions.forage(a, w, rng=random.Random(0))
    assert a.cargo == needs.CARRY_MAX
    # Only the 1 unit of pouch room was actually taken from the tile,
    # even though FORAGE_TILE_DEPLETION would normally take more.
    assert tile.resource_amount == 9.0


def test_forage_full_hunger_but_empty_cargo_still_forages():
    # A sated agent can still stockpile for the colony.
    a = Agent('A', 0, 0, agent_id=1, colony_id=1)
    a.hunger = needs.NEED_MAX
    w = _grass_world()
    tile = _food_tile(w, 0, 0, amount=10.0)
    event = actions.forage(a, w, rng=random.Random(0))
    assert event['type'] == 'foraged'
    assert a.cargo == needs.FORAGE_TILE_DEPLETION
    assert tile.resource_amount < 10.0


def test_forage_full_hunger_and_full_cargo_idles():
    a = Agent('A', 0, 0, agent_id=1, colony_id=1)
    a.hunger = needs.NEED_MAX
    a.cargo = needs.CARRY_MAX
    w = _grass_world()
    tile = _food_tile(w, 0, 0, amount=10.0)
    event = actions.forage(a, w, rng=random.Random(0))
    assert event['type'] == 'idled'
    # Tile untouched — no silent depletion when both buffers are full.
    assert tile.resource_amount == 10.0


# ─── deposit at camp ──────────────────────────────────────────────────

def test_deposit_moves_cargo_into_colony_stock():
    c = _colony(food_stock=20)
    a = Agent('A', 0, 0, agent_id=1, colony_id=1)
    a.cargo = 5
    event = actions.deposit_cargo(a, c)
    assert event['type'] == 'deposited'
    assert a.cargo == 0
    assert c.food_stock == 25


def test_deposit_sets_agent_state_depositing():
    c = _colony(food_stock=20)
    a = Agent('A', 0, 0, agent_id=1, colony_id=1)
    a.cargo = 5
    actions.deposit_cargo(a, c)
    assert a.state == actions.STATE_DEPOSITING


def test_deposit_off_camp_returns_idled_no_mutation():
    c = _colony(cx=0, cy=0, food_stock=20)
    a = Agent('A', 3, 3, agent_id=1, colony_id=1)  # not at camp
    a.cargo = 5
    event = actions.deposit_cargo(a, c)
    assert event['type'] == 'idled'
    assert a.cargo == 5
    assert c.food_stock == 20


def test_deposit_empty_cargo_returns_idled():
    c = _colony(food_stock=20)
    a = Agent('A', 0, 0, agent_id=1, colony_id=1)
    a.cargo = 0
    event = actions.deposit_cargo(a, c)
    assert event['type'] == 'idled'
    assert c.food_stock == 20


# ─── decide_action routes through the carry loop ──────────────────────

def test_day_at_camp_with_cargo_returns_deposit():
    c = _colony(cx=0, cy=0)
    w = _grass_world()
    a = Agent('A', 0, 0, agent_id=1, colony_id=1)
    a.cargo = 3
    # Needs all comfortable so the carry rule is the one that fires.
    a.hunger = 90
    a.energy = 90
    a.social = 90
    a.health = 90
    action_name = decide_action(a, world=w, colony=c, phase='day').action
    assert action_name == 'deposit'


def test_day_full_cargo_non_rogue_returns_home_to_deposit():
    """Non-rogue agents with a full pouch DO head home. The 'remove
    forced returns' rework dropped all camp-seeking, but a full pouch
    is a special signal: the agent literally can't gather more until
    they offload. Letting them wander the field with CARRY_MAX cargo
    wasted whole days of productivity. Rogues are still exempt — no
    home to go to — and get routed through eat_cargo / explore instead.
    """
    c = _colony(cx=0, cy=0)
    w = _grass_world(6, 6)
    a = Agent('A', 4, 4, agent_id=1, colony_id=1)  # off camp
    a.cargo = needs.CARRY_MAX
    a.hunger = 90
    a.energy = 90
    a.social = 90
    a.health = 90
    action_name = decide_action(a, world=w, colony=c, phase='day').action
    assert action_name == 'step_to_camp'


def test_day_full_cargo_rogue_does_not_force_return():
    """Rogue has no home. A full pouch routes them to eat_cargo when
    hungry or explore otherwise — never step_to_camp."""
    c = _colony(cx=0, cy=0)
    w = _grass_world(6, 6)
    a = Agent('A', 4, 4, agent_id=1, colony_id=1)
    a.rogue = True
    a.cargo = needs.CARRY_MAX
    a.hunger = 90
    a.energy = 90
    a.social = 90
    a.health = 90
    action_name = decide_action(a, world=w, colony=c, phase='day').action
    assert action_name != 'step_to_camp'


def test_day_partial_cargo_off_camp_does_not_force_return():
    """Only FULL cargo forces a return. A half-full pouch keeps the
    agent productive — otherwise every couple of forages they'd stop
    working and trudge home, same flat-demo failure mode as before."""
    c = _colony(cx=0, cy=0)
    w = _grass_world(6, 6)
    a = Agent('A', 4, 4, agent_id=1, colony_id=1)
    a.cargo = needs.CARRY_MAX // 2
    a.hunger = 90
    a.energy = 90
    a.social = 90
    a.health = 90
    action_name = decide_action(a, world=w, colony=c, phase='day').action
    assert action_name != 'step_to_camp'
    assert action_name == 'plant'
