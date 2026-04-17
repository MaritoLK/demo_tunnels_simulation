"""Terrain movement cost: destination terrain sets move_cooldown after step.

Costs: grass=1, forest=2, sand=2, stone=3. Cost N = one successful step
consumes N ticks. Implementation: after step, agent.move_cooldown = N - 1.
Next N-1 ticks the agent emits `idled` (traversing) and skips decide_action.
"""
import random

from app.engine import actions, needs
from app.engine.agent import Agent, tick_agent
from app.engine.colony import EngineColony
from app.engine.world import Tile, World


def _world_with_terrain(center_terrain='grass'):
    """5x5 grass world with (2,2) replaced by center_terrain. Agent starts at (1,2)."""
    w = World(5, 5)
    w.tiles = [[Tile(x, y, 'grass') for x in range(5)] for y in range(5)]
    w.tiles[2][2].terrain = center_terrain
    return w


def _colony():
    return EngineColony(1, 'R', '#000', camp_x=0, camp_y=0, food_stock=100)


def test_agent_has_move_cooldown_slot_defaulting_zero():
    a = Agent(name='A', x=0, y=0, colony_id=1)
    assert a.move_cooldown == 0


def test_step_into_grass_zero_cooldown():
    a = Agent('A', 1, 2, agent_id=1, colony_id=1)
    w = _world_with_terrain('grass')
    moved = actions.step_toward(a, 2, 2, w)
    assert moved is True
    assert (a.x, a.y) == (2, 2)
    assert a.move_cooldown == 0


def test_step_into_forest_cooldown_one():
    a = Agent('A', 1, 2, agent_id=1, colony_id=1)
    w = _world_with_terrain('forest')
    actions.step_toward(a, 2, 2, w)
    assert (a.x, a.y) == (2, 2)
    assert a.move_cooldown == 1


def test_step_into_sand_cooldown_one():
    a = Agent('A', 1, 2, agent_id=1, colony_id=1)
    w = _world_with_terrain('sand')
    actions.step_toward(a, 2, 2, w)
    assert (a.x, a.y) == (2, 2)
    assert a.move_cooldown == 1


def test_step_into_stone_cooldown_two():
    a = Agent('A', 1, 2, agent_id=1, colony_id=1)
    w = _world_with_terrain('stone')
    actions.step_toward(a, 2, 2, w)
    assert (a.x, a.y) == (2, 2)
    assert a.move_cooldown == 2


def test_explore_sets_cooldown_for_destination_terrain():
    a = Agent('A', 2, 2, agent_id=1, colony_id=1)
    w = _world_with_terrain('grass')
    w.tiles[2][3].terrain = 'sand'
    w.tiles[2][1].terrain = 'stone'
    w.tiles[1][2].terrain = 'grass'
    w.tiles[3][2].terrain = 'grass'
    rng = random.Random(0)
    for _ in range(20):
        a.x, a.y = 2, 2
        a.move_cooldown = 0
        actions.explore(a, w, rng=rng)
        dest_terrain = w.get_tile(a.x, a.y).terrain
        expected = actions.TERRAIN_MOVE_COST[dest_terrain] - 1
        assert a.move_cooldown == expected, (
            f"landed on {dest_terrain} at ({a.x},{a.y}), cooldown {a.move_cooldown} != {expected}"
        )


def test_tick_with_cooldown_decrements_and_skips_action():
    a = Agent('A', 2, 2, agent_id=1, colony_id=1)
    a.move_cooldown = 2
    a.hunger = 20.0  # below HUNGER_MODERATE → would trigger forage if not gated
    w = _world_with_terrain('grass')
    rng = random.Random(0)
    events = tick_agent(a, w, [a], {1: _colony()}, phase='day', rng=rng)
    assert a.move_cooldown == 1
    assert (a.x, a.y) == (2, 2)  # no movement
    assert any(e.get('type') == 'idled' for e in events)


def test_tick_cooldown_expires_then_agent_acts():
    """Tick 1: cooldown decrements to 0, emits idled (traversing).
    Tick 2: cooldown already 0 → decide_action runs, emits non-traversal event."""
    a = Agent('A', 2, 2, agent_id=1, colony_id=1)
    a.move_cooldown = 1
    w = _world_with_terrain('grass')
    rng = random.Random(0)
    events_tick1 = tick_agent(a, w, [a], {1: _colony()}, phase='day', rng=rng)
    assert a.move_cooldown == 0
    assert any('traversing' in e.get('description', '') for e in events_tick1)

    events_tick2 = tick_agent(a, w, [a], {1: _colony()}, phase='day', rng=rng)
    # Second tick emitted a real engine action (planted/moved/foraged/etc.),
    # NOT the cooldown-traversal idle event.
    assert not any('traversing' in e.get('description', '') for e in events_tick2)


def test_tick_with_cooldown_sets_traversing_state():
    """Frontend relies on agent.state == 'traversing' to render the
    traversal tint. Must be set during every cooldown tick."""
    a = Agent('A', 2, 2, agent_id=1, colony_id=1)
    a.move_cooldown = 2
    a.state = actions.STATE_FORAGING  # prior intent before entering rough tile
    w = _world_with_terrain('grass')
    rng = random.Random(0)
    tick_agent(a, w, [a], {1: _colony()}, phase='day', rng=rng)
    assert a.state == actions.STATE_TRAVERSING


def test_cooldown_decay_still_happens_during_traversal():
    """Needs decay runs even when cooldown blocks action.
    Otherwise sand/stone would be a free hunger shelter."""
    a = Agent('A', 2, 2, agent_id=1, colony_id=1)
    a.move_cooldown = 1
    a.hunger = 80.0
    w = _world_with_terrain('grass')
    rng = random.Random(0)
    tick_agent(a, w, [a], {1: _colony()}, phase='day', rng=rng)
    assert 80.0 - a.hunger == needs.HUNGER_DECAY
