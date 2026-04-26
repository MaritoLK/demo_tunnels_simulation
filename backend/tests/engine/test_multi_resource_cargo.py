"""Multi-resource cargo: agents pouch food/wood/stone with per-unit
weight (1/2/3) capped at CARRY_MAX. Gather actions add to the agent's
own pouch; deposit drains all three pouches into the colony stocks.

Pre-refactor only food was carried — gather_wood/stone went straight
to colony.wood_stock / stone_stock. The user wants agents to act as
workers: gather → carry → deposit. Heavier resources fill faster, so
a stone-gathering trip can ferry less mass than a food trip.
"""
from app.engine import actions, needs
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


def test_agent_has_three_cargo_slots():
    a = Agent(name='A', x=0, y=0, agent_id=1, colony_id=1)
    assert a.cargo_food == 0
    assert a.cargo_wood == 0
    assert a.cargo_stone == 0


def test_cargo_weight_helper():
    a = Agent(name='A', x=0, y=0, agent_id=1, colony_id=1)
    a.cargo_food = 2
    a.cargo_wood = 1
    a.cargo_stone = 1
    # 2*1 + 1*2 + 1*3 = 7
    assert needs.cargo_weight(a) == 7


def test_weight_constants_exposed():
    assert needs.FOOD_WEIGHT == 1
    assert needs.WOOD_WEIGHT == 2
    assert needs.STONE_WEIGHT == 3


def test_gather_wood_fills_pouch_not_colony():
    world = _grass()
    colony = _colony()
    tile = world.get_tile(5, 5)
    tile.resource_type = 'wood'
    tile.resource_amount = 5.0
    a = Agent(name='A', x=5, y=5, agent_id=1, colony_id=1)
    actions.gather_wood(a, world, colony)
    assert a.cargo_wood > 0, 'wood gather must credit pouch, not colony'
    assert colony.wood_stock == 0, 'colony stock filled directly — refactor regressed'


def test_gather_stone_fills_pouch_not_colony():
    world = _grass()
    colony = _colony()
    tile = world.get_tile(5, 5)
    tile.resource_type = 'stone'
    tile.resource_amount = 5.0
    a = Agent(name='A', x=5, y=5, agent_id=1, colony_id=1)
    actions.gather_stone(a, world, colony)
    assert a.cargo_stone > 0
    assert colony.stone_stock == 0


def test_deposit_drains_all_three_pouches():
    world = _grass()
    colony = _colony()
    a = Agent(name='A', x=0, y=0, agent_id=1, colony_id=1)
    a.cargo_food = 3.0
    a.cargo_wood = 2.0
    a.cargo_stone = 1.0
    actions.deposit_cargo(a, colony)
    assert colony.food_stock == 3.0
    assert colony.wood_stock == 2.0
    assert colony.stone_stock == 1.0
    assert a.cargo_food == 0
    assert a.cargo_wood == 0
    assert a.cargo_stone == 0


def test_decide_action_cargo_full_uses_weight():
    # 4 wood × 2 = 8 = CARRY_MAX → cargo full, must head to camp.
    world = _grass()
    colony = EngineColony(id=1, name='Red', color='#e74c3c', camp_x=0, camp_y=0, food_stock=0)
    a = Agent(name='A', x=5, y=5, agent_id=1, colony_id=1)
    a.cargo_wood = 4.0
    decision = decide_action(a, world, colony, 'day')
    assert decision.action == 'step_to_camp', (
        f'4 wood = 8 weight = full, expected step_to_camp, got {decision.action!r}'
    )


def test_decide_action_cargo_partial_does_not_force_return():
    # 2 stone × 3 = 6 < CARRY_MAX (8). Still room. Don't force home.
    world = _grass()
    colony = EngineColony(id=1, name='Red', color='#e74c3c', camp_x=0, camp_y=0, food_stock=0)
    a = Agent(name='A', x=5, y=5, agent_id=1, colony_id=1)
    a.cargo_stone = 2.0
    a.hunger = 80.0
    a.energy = 80.0
    a.social = 80.0
    decision = decide_action(a, world, colony, 'day')
    assert decision.action != 'step_to_camp', (
        f'partial cargo (weight 6/8) must not force return, got {decision.reason!r}'
    )


def test_gather_wood_skips_when_no_pouch_room_for_wood():
    # Agent cargo weight 7 (7 food). Wood costs 2 weight per unit.
    # No room for even 1 wood, so gather_wood returns idled.
    world = _grass()
    colony = _colony()
    tile = world.get_tile(5, 5)
    tile.resource_type = 'wood'
    tile.resource_amount = 5.0
    a = Agent(name='A', x=5, y=5, agent_id=1, colony_id=1)
    a.cargo_food = 7.0
    out = actions.gather_wood(a, world, colony)
    assert out['type'] == 'idled', f'no-room gather_wood must idle, got {out}'
    assert a.cargo_wood == 0


def test_eat_cargo_consumes_food_only():
    # eat_cargo should pull from cargo_food, leaving wood / stone alone.
    world = _grass()
    a = Agent(name='A', x=5, y=5, agent_id=1, colony_id=1)
    a.hunger = 5.0
    a.cargo_food = 2.0
    a.cargo_wood = 1.0
    a.cargo_stone = 1.0
    out = actions.eat_cargo(a)
    assert out['type'] == 'ate_from_cargo'
    assert a.cargo_food == 1.0, 'eat_cargo must consume exactly one food unit'
    assert a.cargo_wood == 1.0, 'eat_cargo must not touch wood'
    assert a.cargo_stone == 1.0, 'eat_cargo must not touch stone'


def test_gather_wood_sets_chopping_state():
    # The wire/UI distinction: foraging = food, chopping = wood,
    # mining = stone. Without a distinct state the renderer can't
    # telegraph the worker role.
    world = _grass()
    colony = _colony()
    tile = world.get_tile(5, 5)
    tile.resource_type = 'wood'
    tile.resource_amount = 5.0
    a = Agent(name='A', x=5, y=5, agent_id=1, colony_id=1)
    actions.gather_wood(a, world, colony)
    assert a.state == 'chopping', f'expected chopping, got {a.state!r}'


def test_gather_stone_sets_mining_state():
    world = _grass()
    colony = _colony()
    tile = world.get_tile(5, 5)
    tile.resource_type = 'stone'
    tile.resource_amount = 5.0
    a = Agent(name='A', x=5, y=5, agent_id=1, colony_id=1)
    actions.gather_stone(a, world, colony)
    assert a.state == 'mining', f'expected mining, got {a.state!r}'


def test_eat_cargo_with_no_food_idles_even_if_wood_present():
    # Wood/stone aren't food. An agent holding only wood can't eat.
    a = Agent(name='A', x=5, y=5, agent_id=1, colony_id=1)
    a.hunger = 5.0
    a.cargo_food = 0.0
    a.cargo_wood = 4.0
    out = actions.eat_cargo(a)
    assert out['type'] == 'idled', (
        f'expected idled when only wood is in pouch, got {out}'
    )
