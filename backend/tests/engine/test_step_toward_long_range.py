"""step_toward must reach a camp anywhere on the map.

Pre-fix bug: PATH_SEARCH_HORIZON=40 capped BFS depth. On a 60×60 map
with cardinal-only moves an agent at (55,55) is Manhattan 104 from a
camp at (3,3) — BFS runs out of depth, step_toward returns False,
agent idles forever with a full cargo.

The 1700-tick diagnostic on 2026-04-26 showed 15/20 agents in this
state by the end of the run. The fix is to drop the horizon cap on
the known-target BFS — the closed walkable graph is the natural
termination bound, no need to clip depth.
"""
from app.engine import actions
from app.engine.agent import Agent
from app.engine.world import Tile, World


def _grass(width, height):
    w = World(width, height)
    w.tiles = [
        [Tile(x, y, 'grass') for x in range(width)]
        for y in range(height)
    ]
    return w


def test_step_toward_camp_from_far_corner_succeeds():
    # 60×60 grass map. Camp at (3,3). Agent at (55,55). Manhattan = 104.
    world = _grass(60, 60)
    agent = Agent(name='A', x=55, y=55, agent_id=1, colony_id=1)
    moved = actions.step_toward(agent, 3, 3, world)
    assert moved, 'step_toward must succeed across a fully-walkable 60×60 map'
    # Agent moved one tile toward camp (toward smaller coords).
    assert agent.x <= 55 and agent.y <= 55, (
        f'agent moved AWAY from camp: ({agent.x},{agent.y})'
    )
    assert (agent.x, agent.y) != (55, 55), 'no actual movement recorded'


def test_step_toward_succeeds_at_max_world_diagonal():
    # 100×100 — bigger than the demo's standard. Step from one corner
    # toward the opposite. Manhattan distance = 198. Must still resolve.
    world = _grass(100, 100)
    agent = Agent(name='A', x=99, y=99, agent_id=1, colony_id=1)
    moved = actions.step_toward(agent, 0, 0, world)
    assert moved, '100×100 corner-to-corner step_toward must succeed'


def test_step_toward_blocked_by_water_returns_false():
    # Sanity: step_toward still returns False when the target is genuinely
    # unreachable. Build a world where a 1-tile-wide water strip cuts the
    # agent off from the camp — no walkable path exists.
    world = _grass(20, 20)
    # Vertical water strip at x=10 blocks every row.
    for y in range(20):
        t = world.get_tile(10, y)
        t.terrain = 'water'
    agent = Agent(name='A', x=15, y=10, agent_id=1, colony_id=1)
    moved = actions.step_toward(agent, 5, 10, world)
    assert not moved, 'step_toward should fail when target is unreachable'
