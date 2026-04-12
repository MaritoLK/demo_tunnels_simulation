"""
Audit Bug #3 — tick_agent sets agent.state = 'resting' when energy<=0 (agent.py:61-62),
but the assignment is immediately overwritten on every execution path:

  * energy<=0 is trivially below ENERGY_CRITICAL=15, so decide_action returns 'rest'
    on the very next line → execute_action calls actions.rest(agent), which sets
    agent.state = 'resting' (actions.py:81). Double-write with the same value.
  * If health<=0 on the same tick, actions.die(agent) sets agent.state = 'dead'
    (actions.py:122). The 'resting' assignment is overwritten with 'dead'.

Claim: removing lines 61-62 changes the final observable state for NO tick.

Test: snapshot agent.state after one tick in two scenarios (low energy and
low-energy-also-dead), then repeat with the lines removed via monkey-patch of
the module. Compare outputs.
"""
import random

from app.engine.world import Tile, World
from app.engine.agent import Agent
from app.engine import agent as agent_module


def build_world():
    w = World(3, 3)
    w.tiles = [[Tile(x, y, 'grass') for x in range(3)] for y in range(3)]
    return w


def snapshot(label, tick_fn):
    w = build_world()
    rng = random.Random(0)
    # Scenario A: low energy only (should end up resting)
    a = Agent('A', 1, 1)
    a.energy = 0.0
    a.state = 'sentinel-A'
    tick_fn(a, w, [a], rng=rng)

    # Scenario B: low energy AND dead from starvation (should end up dead)
    b = Agent('B', 1, 1)
    b.energy = 0.0
    b.hunger = 0.0
    b.health = 1.0  # decay will knock it to -1 → death branch
    b.state = 'sentinel-B'
    tick_fn(b, w, [b], rng=rng)

    print(f'[{label}] A.state={a.state!r} A.alive={a.alive} B.state={b.state!r} B.alive={b.alive}')
    return (a.state, a.alive, b.state, b.alive)


def tick_with_dead_lines_removed(agent, world, all_agents, *, rng):
    # Inline copy of tick_agent minus the dead lines 61-62.
    if not agent.alive:
        return []
    events = []
    agent_module.needs.decay_needs(agent)
    if agent.health <= 0:
        events.append(agent_module.actions.die(agent))
        return events
    action_name = agent_module.decide_action(agent)
    events.append(agent_module.execute_action(action_name, agent, world, all_agents, rng=rng))
    agent.age += 1
    return events


def main():
    with_lines = snapshot('original  ', agent_module.tick_agent)
    without_lines = snapshot('lines 61-62 removed', tick_with_dead_lines_removed)

    identical = with_lines == without_lines
    print(f'\nfinal observable state identical: {identical}')


if __name__ == '__main__':
    main()
