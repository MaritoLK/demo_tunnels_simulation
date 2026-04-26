"""Regression: agents oscillating around their food-memory tile.

Pre-fix: memory-biased explore picked the nearest remembered tile as
target. When the agent was ALREADY on that tile, step_toward returned
False, the function fell to random walk, the agent moved to a
neighbour. Next tick the same memory entry pulled them back. Result:
a 2-tick loop chewing through energy with zero useful work.

Fix expectations:
  * If every memory entry is the agent's current tile, explore must
    NOT random-walk.
  * Frontier scouting (when a colony reference is available) prefers
    walkable neighbours OUTSIDE colony.explored so explore actually
    advances the fog frontier.
  * Random walk stays only as the final fallback (no memory, no
    unexplored neighbour, no colony reference).
"""
import random

from app.engine import actions
from app.engine.agent import Agent
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


def _set_food(world, x, y, amount):
    t = world.tiles[y][x]
    t.resource_type = 'food'
    t.resource_amount = amount
    return t


def test_explore_does_not_oscillate_when_agent_is_on_only_memory_tile():
    # Agent stands on its single remembered food tile. Pre-fix: explore
    # would step_toward(self), get False, fall to random walk and burn
    # energy. Post-fix: the memory entry is filtered (== self) and the
    # function either scouts an unexplored neighbour OR idles. It must
    # NOT pick a random walkable neighbour and emit a 'moved' event.
    a = Agent(name='A', x=5, y=5, agent_id=1, colony_id=1)
    w = _grass()
    _set_food(w, 5, 5, 10.0)
    a.food_memory = [(5, 5)]
    colony = _colony()
    # Mark every neighbour as already-explored so frontier scouting has
    # nothing to chase — forces the path to the idle branch, which is
    # the energy-conserving result we want when there's nothing to do.
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            nx, ny = 5 + dx, 5 + dy
            if 0 <= nx < 10 and 0 <= ny < 10:
                colony.explored.add((nx, ny))
    pre = (a.x, a.y)
    ev = actions.explore(a, w, colony, rng=random.Random(0))
    assert (a.x, a.y) == pre, (
        f'agent moved from {pre} to {(a.x, a.y)} — expected to idle in place'
    )
    assert ev['type'] == 'idled'


def test_explore_scouts_unexplored_neighbour_when_at_memory_tile():
    # Same setup, but neighbours are NOT in colony.explored. Frontier
    # scouting should kick in and walk the agent toward fresh fog
    # rather than oscillating.
    a = Agent(name='A', x=5, y=5, agent_id=1, colony_id=1)
    w = _grass()
    _set_food(w, 5, 5, 10.0)
    a.food_memory = [(5, 5)]
    colony = _colony()
    # Only the agent's own tile is "explored" (typical mid-game state).
    colony.explored.add((5, 5))
    ev = actions.explore(a, w, colony, rng=random.Random(0))
    assert (a.x, a.y) != (5, 5), 'agent should have stepped onto a neighbour'
    assert ev['type'] == 'moved'
    moved_to = (a.x, a.y)
    # The chosen neighbour must be unexplored.
    assert moved_to not in colony.explored


def test_explore_picks_other_memory_tile_when_one_is_underfoot():
    # Two remembered tiles — one is the agent's current position, the
    # other isn't. step_toward on the second should succeed and the
    # agent should move toward it instead of falling to random walk.
    a = Agent(name='A', x=5, y=5, agent_id=1, colony_id=1)
    w = _grass()
    _set_food(w, 5, 5, 10.0)
    _set_food(w, 8, 5, 10.0)
    a.food_memory = [(5, 5), (8, 5)]
    colony = _colony()
    ev = actions.explore(a, w, colony, rng=random.Random(0))
    assert ev['type'] == 'moved'
    # Should step toward (8,5), so x increased, y unchanged.
    assert a.x > 5
    assert a.y == 5


def test_explore_random_walk_fallback_still_works_when_no_memory_and_no_colony():
    # Legacy call site (forage's no-food fallback) doesn't pass colony.
    # Behaviour must remain a random walk so existing routing keeps
    # working — the fix only adds the new frontier branch when colony
    # IS available.
    a = Agent(name='A', x=5, y=5, agent_id=1, colony_id=1)
    w = _grass()
    assert a.food_memory == []
    ev = actions.explore(a, w, rng=random.Random(0))
    assert ev['type'] == 'moved'
    # Agent moved to one of the four neighbours.
    assert (a.x, a.y) != (5, 5)
    assert abs(a.x - 5) + abs(a.y - 5) == 1
