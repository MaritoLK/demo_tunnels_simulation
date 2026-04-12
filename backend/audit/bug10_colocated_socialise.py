"""
Audit Correctness #2 — adjacent_agent required Manhattan distance == 1,
so two agents sharing the same tile (distance 0) could never socialise.

Bug matters because:
  * spawn_agent has no occupancy check (see bug #11), so agents routinely
    share tiles on small worlds.
  * explore / step_toward don't block co-location, so agents naturally
    end up on the same tile during a run.
Once co-located, social decays forever; no mechanism restores it.

Test: 1x1 grass world, two agents on (0,0), social seeded below SOCIAL_LOW
so decide_action picks 'socialise'. One tick each.
  Pre-fix: 'idled' event, social unchanged.
  Post-fix: 'socialised' event, both agents' social restored.
"""
import random

from app.engine import actions, needs
from app.engine.agent import Agent, tick_agent
from app.engine.world import World, Tile


def flat_world():
    w = World(1, 1)
    w.tiles = [[Tile(0, 0, 'grass')]]
    return w


def legacy_adjacent_agent(agent, agents):
    """Pre-fix: Manhattan distance must equal 1 (excludes co-location)."""
    for other in agents:
        if other is agent or not other.alive:
            continue
        if abs(other.x - agent.x) + abs(other.y - agent.y) == 1:
            return other
    return None


def run_trial(use_legacy):
    original = actions.adjacent_agent
    if use_legacy:
        actions.adjacent_agent = legacy_adjacent_agent
    try:
        world = flat_world()
        a = Agent('Alice', 0, 0)
        b = Agent('Bob', 0, 0)
        a.social = needs.SOCIAL_LOW - 1
        b.social = needs.SOCIAL_LOW - 1
        rng = random.Random(0)
        events = tick_agent(a, world, [a, b], rng=rng)
        return events[-1]['type'], a.social, b.social
    finally:
        actions.adjacent_agent = original


def report(label, event_type, a_social, b_social):
    print(f'{label}')
    print(f"  event          : {event_type}")
    print(f'  Alice social   : {a_social:.1f}')
    print(f'  Bob social     : {b_social:.1f}')
    print()


def main():
    print('1x1 world, Alice and Bob both at (0,0), both socially starved.\n')
    report('Pre-fix  (== 1)', *run_trial(use_legacy=True))
    report('Post-fix (<= 1)', *run_trial(use_legacy=False))


if __name__ == '__main__':
    main()
