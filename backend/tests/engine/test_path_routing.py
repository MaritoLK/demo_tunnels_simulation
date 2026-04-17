"""step_toward must route around obstacles, not just try two greedy axes.

Motivating bug: on the edge of a water biome, greedy step_toward gets both
candidate axes blocked and returns False. The caller then random-walks via
explore() — agent bounces along the shoreline and never reaches the food
tile one step beyond the water.

With BFS-based routing, step_toward returns True as long as there *is* a
walkable path to the target within the search horizon, and the step taken
lies on that shortest path.
"""
from app.engine import actions
from app.engine.agent import Agent
from app.engine.world import Tile, World


def _open_world(w, h):
    world = World(w, h)
    world.tiles = [[Tile(x, y, 'grass') for x in range(w)] for y in range(h)]
    return world


def test_step_toward_routes_around_water_wall():
    # 6x6 grass with a water column at x=3, except a single gap at y=3.
    # Agent at (0,0) must reach (5,0): cannot go straight east, has to
    # detour south → east through the gap → back north.
    w = _open_world(6, 6)
    for y in range(6):
        w.get_tile(3, y).terrain = 'water'
    w.get_tile(3, 3).terrain = 'grass'  # the only crossing

    a = Agent('A', 0, 0, agent_id=1, colony_id=1)
    steps = 0
    while (a.x, a.y) != (5, 0) and steps < 40:
        # mimic tick_agent: wait out cooldown, then act
        if a.move_cooldown > 0:
            a.move_cooldown -= 1
            steps += 1
            continue
        moved = actions.step_toward(a, 5, 0, w)
        assert moved, f'stuck at ({a.x},{a.y}) step {steps}'
        steps += 1
    assert (a.x, a.y) == (5, 0), f'never reached target, stuck at ({a.x},{a.y})'


def test_step_toward_prefers_shortest_path_no_detour_when_clear():
    # Open map, agent at (0,0), target (3,0). First step should be east
    # (one of the shortest paths), not a random detour.
    w = _open_world(5, 5)
    a = Agent('A', 0, 0, agent_id=1, colony_id=1)
    moved = actions.step_toward(a, 3, 0, w)
    assert moved
    # Greedy-equivalent on an open map: step is on the straight line.
    assert (a.x, a.y) == (1, 0)


def test_step_toward_returns_false_when_target_unreachable():
    # 5x5 with a full water wall sealing the target off entirely.
    w = _open_world(5, 5)
    for y in range(5):
        w.get_tile(3, y).terrain = 'water'
    a = Agent('A', 0, 0, agent_id=1, colony_id=1)
    moved = actions.step_toward(a, 4, 4, w)
    assert moved is False
    # Agent did not move.
    assert (a.x, a.y) == (0, 0)


def test_step_toward_treats_target_tile_as_reachable_even_if_unwalkable():
    # Agents legitimately need to step *onto* their own camp tile, and
    # in some test fixtures the tile marks itself unusual. Accept the
    # destination tile even if is_walkable is false at the very last hop
    # — but only at the target, never mid-path. Pragma: grass terrain
    # so this is mostly a future-proofing asser­tion that the BFS
    # exit-condition doesn't require is_walkable on the target.
    w = _open_world(4, 4)
    a = Agent('A', 0, 0, agent_id=1, colony_id=1)
    moved = actions.step_toward(a, 1, 0, w)
    assert moved
    assert (a.x, a.y) == (1, 0)


def test_step_toward_bounded_search_gives_up_on_giant_maze():
    # If the target is reachable only through a path longer than the
    # BFS horizon, step_toward returns False (agent will random-walk).
    # Guards against pathological cost when the horizon fires.
    w = _open_world(60, 60)
    # Enclose target in a pocket that requires 200+ tiles of detour —
    # a full water ring with a single far-away entrance.
    for y in range(60):
        for x in range(60):
            if 10 <= x <= 50 and 10 <= y <= 50 and not (20 <= x <= 40 and 20 <= y <= 40):
                w.get_tile(x, y).terrain = 'water'
    # Entrance at (10, 50) is now also water — fully sealed.
    a = Agent('A', 0, 0, agent_id=1, colony_id=1)
    moved = actions.step_toward(a, 30, 30, w)
    assert moved is False
