"""Regression: agents oscillating around their food-memory tile, and the
follow-up "agents idle on top of food while unexplored fog still
exists" / "agents revisit already-explored tiles" reports.

Pre-fix history:
  * Memory-biased explore picked the nearest remembered tile as target.
    Standing on that tile, step_toward(self) returned False and the
    function fell to random walk. Two-tick loop burning energy.
  * The first patch filtered self-targets and added a frontier-scout
    branch — BUT it only checked IMMEDIATE neighbours. With a reveal
    radius of 1 every neighbour was already in colony.explored after
    a single visit, so the agent idled instead of scouting onward; OR
    fell to random walk (when memory was empty) and revisited known
    territory.

Fix expectations:
  * Memory still takes priority over scouting (known food beats fog).
  * Frontier scouting does a BFS for the nearest REACHABLE unexplored
    tile and steps toward it — so an agent in the middle of a cleared
    bubble pushes outward instead of pacing in place or random-walking
    over already-mapped ground.
  * Idle is only legitimate when the entire reachable walkable map has
    been mapped. Anything less and the agent should be moving the
    frontier outward.
  * Random walk stays as the final fallback only when no colony
    reference is supplied (forage's no-food fallback path).
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


def test_explore_steps_toward_distant_unexplored_when_neighbours_mapped():
    # Agent stands on its only remembered food tile. The 3x3 bubble
    # around the agent is already in colony.explored (typical state
    # after a forage cycle on a tile with reveal radius 1). Tiles
    # further out are still fogged. Pre-fix: agent idled because the
    # frontier scout only looked at immediate neighbours. Post-fix:
    # BFS finds (3,5) is unexplored and the agent steps west toward
    # it via (4,5), pushing the frontier outward.
    a = Agent(name='A', x=5, y=5, agent_id=1, colony_id=1)
    w = _grass()
    _set_food(w, 5, 5, 10.0)
    a.food_memory = [(5, 5)]
    colony = _colony()
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            nx, ny = 5 + dx, 5 + dy
            if 0 <= nx < 10 and 0 <= ny < 10:
                colony.explored.add((nx, ny))
    ev = actions.explore(a, w, colony, rng=random.Random(0))
    assert ev['type'] == 'moved', (
        f"expected 'moved', got {ev['type']} — agent idled while "
        f"unexplored fog remained beyond the 3x3 bubble"
    )
    assert (a.x, a.y) != (5, 5)
    # Agent moved one step (Manhattan 1) toward the frontier.
    assert abs(a.x - 5) + abs(a.y - 5) == 1


def test_explore_idles_only_when_entire_reachable_map_is_explored():
    # No fog left to chase — every walkable tile in the world is in
    # colony.explored. Idle is the right answer here: nothing to scout,
    # don't burn energy random-walking over known ground.
    a = Agent(name='A', x=2, y=2, agent_id=1, colony_id=1)
    w = _grass(width=5, height=5)
    a.food_memory = [(2, 2)]
    colony = _colony()
    for x in range(5):
        for y in range(5):
            colony.explored.add((x, y))
    pre = (a.x, a.y)
    ev = actions.explore(a, w, colony, rng=random.Random(0))
    assert ev['type'] == 'idled', (
        f"expected 'idled' when whole map mapped, got {ev}"
    )
    assert (a.x, a.y) == pre


def test_explore_progresses_toward_fog_when_inside_explored_bubble():
    # No memory, colony.explored covers a 5x5 bubble around the
    # agent. Pre-fix path: frontier scout checked only immediate
    # neighbours, all explored, so the function fell through to the
    # random-walk fallback and stepped onto an explored tile —
    # exactly the "agents repeat exploration of where they had been
    # already" report. Post-fix: BFS routes outward, the chosen
    # first step is the cardinal neighbour on the shortest path
    # toward unfogged ground. After three more identical calls the
    # agent must be standing on a tile that was previously fogged.
    a = Agent(name='A', x=5, y=5, agent_id=1, colony_id=1)
    w = _grass()
    colony = _colony()
    for dx in range(-2, 3):
        for dy in range(-2, 3):
            nx, ny = 5 + dx, 5 + dy
            if 0 <= nx < 10 and 0 <= ny < 10:
                colony.explored.add((nx, ny))
    # One step of explore — should make Manhattan-1 progress toward
    # the bubble edge.
    ev = actions.explore(a, w, colony, rng=random.Random(0))
    assert ev['type'] == 'moved'
    assert abs(a.x - 5) + abs(a.y - 5) == 1
    # Three more calls — by tick 3 the agent should have crossed
    # the edge of the explored bubble onto a previously fogged
    # tile. (If the function silently revisits explored ground the
    # agent may still be inside the bubble after 4 steps.)
    for _ in range(3):
        actions.explore(a, w, colony, rng=random.Random(0))
    assert (a.x, a.y) not in {
        (x, y)
        for x in range(3, 8)
        for y in range(3, 8)
    }, (
        f'agent at {(a.x, a.y)} after 4 explore calls — still inside '
        f'the pre-explored 5x5 bubble; BFS frontier scout is regressed'
    )


def test_explore_picks_other_memory_tile_when_one_is_underfoot():
    # Two remembered tiles — one is the agent's current position, the
    # other isn't. step_toward on the second should succeed and the
    # agent should move toward it instead of falling to random walk.
    # Memory beats frontier scouting (known food is more valuable
    # than unmapped fog).
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


def test_explore_memory_takes_priority_over_frontier():
    # Memory points east, but a fresh unexplored tile is north. The
    # agent must follow memory first — known food is the higher-value
    # target. Frontier scouting is the explore-when-no-memory branch.
    a = Agent(name='A', x=5, y=5, agent_id=1, colony_id=1)
    w = _grass()
    _set_food(w, 8, 5, 10.0)
    a.food_memory = [(8, 5)]
    colony = _colony()
    # All explored except (5,4) and a strip north — frontier scout
    # would otherwise pull the agent up.
    for x in range(10):
        for y in range(5, 10):
            colony.explored.add((x, y))
    ev = actions.explore(a, w, colony, rng=random.Random(0))
    assert ev['type'] == 'moved'
    assert a.x == 6, f'expected step east toward memory, got x={a.x}'
    assert a.y == 5


def test_explore_random_walk_fallback_still_works_when_no_memory_and_no_colony():
    # Legacy call site (forage's no-food fallback) doesn't pass colony.
    # Behaviour must remain a random walk so existing routing keeps
    # working — the fix only changes the colony-aware branch.
    a = Agent(name='A', x=5, y=5, agent_id=1, colony_id=1)
    w = _grass()
    assert a.food_memory == []
    ev = actions.explore(a, w, rng=random.Random(0))
    assert ev['type'] == 'moved'
    assert (a.x, a.y) != (5, 5)
    assert abs(a.x - 5) + abs(a.y - 5) == 1
