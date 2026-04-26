"""Wood / stone gather + camp tier upgrade.

Closes the loose end where forest and stone tiles were generated and
rendered but no agent action consumed them. New actions:

  * `gather_wood(agent, world, colony)` — agent on wood tile, drains
    GATHER_WOOD_AMOUNT into colony.wood_stock.
  * `gather_stone(agent, world, colony)` — symmetric for stone.
  * `upgrade_camp(agent, colony)` — agent at camp, spend the next
    tier's wood + stone cost, bump colony.tier.

Decision rungs:
  * Inside the at-camp branch, `upgrade_camp` fires when can_upgrade
    holds — between eat_camp and socialise.
  * Own-tile wood / stone gather sits between opportunistic forage
    and plant — direct gain outranks crop investment.

Tier effect: simulation._refresh_fog adds colony.tier to the per-agent
reveal radius, so a tier-2 colony sees a wider area each tick.
"""
import random

from app.engine import actions, config, skill
from app.engine.agent import Agent, decide_action
from app.engine.colony import EngineColony
from app.engine.simulation import Simulation
from app.engine.world import Tile, World


def _world(width=15, height=15):
    w = World(width, height)
    w.tiles = [
        [Tile(x, y, 'grass') for x in range(width)]
        for y in range(height)
    ]
    return w


def _colony(camp_x=5, camp_y=5, food=20, wood=0, stone=0, tier=0):
    c = EngineColony(
        id=1, name='Red', color='#e74c3c',
        camp_x=camp_x, camp_y=camp_y, food_stock=food,
        wood_stock=wood, stone_stock=stone, tier=tier,
    )
    return c


def _agent(x, y):
    a = Agent('A', x, y, agent_id=1, colony_id=1)
    a.hunger = 80.0
    a.energy = 80.0
    a.social = 80.0
    a.health = 100.0
    return a


# ---- gather_wood / gather_stone ------------------------------------------


def test_gather_wood_drains_tile_and_credits_pouch():
    # Post-multi-resource refactor: gather_wood credits the agent's
    # cargo_wood pouch, not the colony directly. Colony stock fills
    # only when the agent deposits at camp.
    a = _agent(8, 5)
    w = _world()
    tile = w.get_tile(8, 5)
    tile.terrain = 'forest'
    tile.resource_type = 'wood'
    tile.resource_amount = 5.0
    colony = _colony()
    pre_pouch = a.cargo_wood
    pre_tile = tile.resource_amount
    ev = actions.gather_wood(a, w, colony)
    assert ev['type'] == 'gathered_wood'
    assert tile.resource_amount == pre_tile - config.GATHER_WOOD_AMOUNT
    assert a.cargo_wood == pre_pouch + config.GATHER_WOOD_AMOUNT
    assert colony.wood_stock == 0, 'colony stock must wait for deposit'


def test_gather_wood_idles_off_wood_tile():
    a = _agent(8, 5)
    w = _world()  # plain grass at (8,5)
    colony = _colony()
    ev = actions.gather_wood(a, w, colony)
    assert ev['type'] == 'idled'
    assert colony.wood_stock == 0


def test_gather_wood_idles_on_depleted_wood_tile():
    a = _agent(8, 5)
    w = _world()
    tile = w.get_tile(8, 5)
    tile.terrain = 'forest'
    tile.resource_type = 'wood'
    tile.resource_amount = 0.0
    ev = actions.gather_wood(a, w, _colony())
    assert ev['type'] == 'idled'


def test_gather_stone_drains_tile_and_credits_pouch():
    a = _agent(2, 5)
    w = _world()
    tile = w.get_tile(2, 5)
    tile.terrain = 'stone'
    tile.resource_type = 'stone'
    tile.resource_amount = 4.0
    colony = _colony()
    ev = actions.gather_stone(a, w, colony)
    assert ev['type'] == 'gathered_stone'
    assert a.cargo_stone == config.GATHER_STONE_AMOUNT
    assert colony.stone_stock == 0, 'colony stock must wait for deposit'


# ---- can_upgrade gate ----------------------------------------------------


def test_can_upgrade_true_when_resources_meet_next_tier_cost():
    next_cost = config.UPGRADE_TIER_COSTS[1]
    colony = _colony(wood=next_cost['wood'], stone=next_cost['stone'])
    assert actions.can_upgrade(colony)


def test_can_upgrade_false_when_below_cost():
    next_cost = config.UPGRADE_TIER_COSTS[1]
    colony = _colony(wood=next_cost['wood'] - 1, stone=next_cost['stone'])
    assert not actions.can_upgrade(colony)


def test_can_upgrade_false_at_max_tier():
    # Stack the colony with absurd resources but pin at max tier —
    # the cap takes priority over the cost check.
    colony = _colony(wood=999, stone=999, tier=config.MAX_COLONY_TIER)
    assert not actions.can_upgrade(colony)


# ---- upgrade_camp action -------------------------------------------------


def test_upgrade_camp_bumps_tier_and_spends_resources():
    next_cost = config.UPGRADE_TIER_COSTS[1]
    colony = _colony(wood=next_cost['wood'] + 5, stone=next_cost['stone'] + 3)
    a = _agent(5, 5)  # at camp
    ev = actions.upgrade_camp(a, colony)
    assert ev['type'] == 'upgraded_camp'
    assert colony.tier == 1
    assert colony.wood_stock == 5
    assert colony.stone_stock == 3


def test_upgrade_camp_idles_off_camp():
    next_cost = config.UPGRADE_TIER_COSTS[1]
    colony = _colony(wood=next_cost['wood'], stone=next_cost['stone'])
    a = _agent(7, 5)  # NOT at camp
    ev = actions.upgrade_camp(a, colony)
    assert ev['type'] == 'idled'
    assert colony.tier == 0


def test_upgrade_camp_idles_when_cant_afford():
    colony = _colony(wood=0, stone=0)
    a = _agent(5, 5)
    ev = actions.upgrade_camp(a, colony)
    assert ev['type'] == 'idled'
    assert colony.tier == 0


def test_upgrade_camp_idles_at_max_tier():
    colony = _colony(wood=999, stone=999, tier=config.MAX_COLONY_TIER)
    a = _agent(5, 5)
    pre_wood = colony.wood_stock
    ev = actions.upgrade_camp(a, colony)
    assert ev['type'] == 'idled'
    assert colony.wood_stock == pre_wood  # no resources spent on a refused upgrade


# ---- decide_action rungs --------------------------------------------------


def test_decide_action_picks_gather_wood_on_wood_tile():
    a = _agent(8, 5)
    w = _world()
    tile = w.get_tile(8, 5)
    tile.terrain = 'forest'
    tile.resource_type = 'wood'
    tile.resource_amount = 10.0
    decision = decide_action(a, w, _colony(), 'day')
    assert decision.action == 'gather_wood'


def test_decide_action_picks_gather_stone_on_stone_tile():
    a = _agent(2, 5)
    w = _world()
    tile = w.get_tile(2, 5)
    tile.terrain = 'stone'
    tile.resource_type = 'stone'
    tile.resource_amount = 10.0
    decision = decide_action(a, w, _colony(), 'day')
    assert decision.action == 'gather_stone'


def test_decide_action_picks_upgrade_camp_when_at_camp_and_affordable():
    next_cost = config.UPGRADE_TIER_COSTS[1]
    colony = _colony(wood=next_cost['wood'], stone=next_cost['stone'])
    a = _agent(5, 5)  # at camp
    decision = decide_action(a, _world(), colony, 'day')
    assert decision.action == 'upgrade_camp'


def test_decide_action_skips_upgrade_when_below_cost():
    colony = _colony(wood=0, stone=0)
    a = _agent(5, 5)
    decision = decide_action(a, _world(), colony, 'day')
    assert decision.action != 'upgrade_camp'


def test_deposit_outranks_upgrade_at_camp():
    # Cargo holding a deposit outranks an at-camp upgrade — the agent
    # should drop their pouch first so the food enters circulation
    # before infrastructure work.
    next_cost = config.UPGRADE_TIER_COSTS[1]
    colony = _colony(wood=next_cost['wood'], stone=next_cost['stone'])
    a = _agent(5, 5)
    a.cargo_food = 4.0
    decision = decide_action(a, _world(), colony, 'day')
    assert decision.action == 'deposit'


# ---- tier effect on fog reveal -------------------------------------------


def test_camp_tier_adds_to_reveal_radius():
    # Simulation._refresh_fog should sum walk-skill radius +
    # colony.tier when painting fog. Verify by stepping a fresh
    # agent (walk-skill 1 = radius 1, 3x3 reveal) under tier 0
    # and tier 2 colonies — the higher tier should reveal more cells.
    def _explored_count(tier):
        w = _world(width=20, height=20)
        c = _colony(camp_x=10, camp_y=10, tier=tier)
        sim = Simulation(w, colonies=[c])
        a = Agent('A', 10, 10, agent_id=1, colony_id=1)
        sim.agents.append(a)
        sim._refresh_fog([a])
        return len(c.explored)

    base = _explored_count(tier=0)
    bumped = _explored_count(tier=2)
    assert bumped > base, (
        f'tier 2 reveal ({bumped} cells) should exceed tier 0 ({base})'
    )
