"""
Audit Py-quality #1 (r3) — every public engine action had `rng=None` as a
default, and `actions.explore` closed the chain with `rng = rng or random`.
That silently reroutes to the process-wide `random` module if any caller
forgets to thread rng through, which would re-introduce the global-random
leak that §9.2 (bug2_rng_leak) fixed at one layer — just one layer higher.

Test: 3x3 grass world, agent in the middle (walkable options in all four
directions). Call explore WITHOUT passing rng, after seeding the global
`random` module to a known value.
  Pre-fix: explore returns an event, agent moves to a position decided by
           the global random stream — reproducible only as long as nobody
           else in the process has touched random.
  Post-fix: explore refuses to run without rng — TypeError on the missing
           keyword-only argument. The engine's reproducibility contract is
           now enforced at the API boundary.
"""
import random

from app.engine import actions
from app.engine.agent import Agent
from app.engine.world import World, Tile


def plain_world():
    w = World(3, 3)
    w.tiles = [[Tile(x, y, 'grass') for x in range(3)] for y in range(3)]
    return w


def legacy_explore(agent, world, rng=None):
    """Pre-fix: silently falls back to the global `random` module."""
    rng = rng or random
    options = []
    for dx, dy in actions.DIRECTIONS:
        nx, ny = agent.x + dx, agent.y + dy
        if world.in_bounds(nx, ny) and world.get_tile(nx, ny).is_walkable:
            options.append((nx, ny))
    if not options:
        agent.state = actions.STATE_IDLE
        return {'type': 'idled', 'description': f'{agent.name} stayed in place'}
    agent.x, agent.y = rng.choice(options)
    agent.state = actions.STATE_EXPLORING
    return {'type': 'moved', 'description': f'{agent.name} moved'}


def run_trial(fn):
    random.seed(42)  # seed global rng to make leakage reproducible
    world = plain_world()
    agent = Agent('Alice', 1, 1)
    try:
        fn(agent, world)
        return 'returned', (agent.x, agent.y), None
    except TypeError as e:
        return 'raised', (agent.x, agent.y), str(e)


def main():
    print('3x3 grass world, agent at (1,1). Calling explore with no rng kwarg.\n')

    outcome, pos, err = run_trial(legacy_explore)
    print(f'Pre-fix  (rng=None default + `rng or random`):')
    print(f'  outcome  : {outcome}')
    print(f'  agent pos: {pos}  <-- determined by global random.seed(42)')
    print()

    outcome, pos, err = run_trial(actions.explore)
    print(f'Post-fix (rng keyword-only required):')
    print(f'  outcome  : {outcome}')
    print(f'  agent pos: {pos}  <-- unchanged; call refused')
    print(f'  error    : {err}')


if __name__ == '__main__':
    main()
