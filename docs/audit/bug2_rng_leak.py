"""
Audit Bug #2 — forage→explore fallback drops rng, leaks to global random.

Setup: all-grass 5x5 world with NO food. An agent with low hunger forages every
tick. find_nearest_tile returns None (no food), forage falls through to explore.

Pre-fix path:   forage(agent, world)  →  explore(agent, world)          # rng=None
                explore does `rng = rng or random`                       # global module
                determinism depends on global random state — not sim.rng

Post-fix path:  forage(agent, world, rng)  →  explore(agent, world, rng=rng)
                determinism is a property of sim.rng alone — global random is irrelevant

Test: run the simulation twice with identical local seed, but with different amounts
of pollution injected into the global `random` module between trials. If determinism
is governed solely by sim.rng (the fix's claim), the two trials are byte-identical.
If it leaks into global random, the runs diverge.
"""
import random

from app.engine.world import Tile, World
from app.engine.agent import Agent, tick_agent


def build_foodless_world():
    w = World(5, 5)
    w.tiles = [
        [Tile(x, y, 'grass') for x in range(5)]
        for y in range(5)
    ]
    return w


def run_trial():
    world = build_foodless_world()
    agent = Agent('A', 2, 2)
    agent.hunger = 10.0  # forces forage branch; no food -> explore fallback
    sim_rng = random.Random(42)  # fresh local rng per trial
    positions = []
    for _ in range(50):
        tick_agent(agent, world, [agent], rng=sim_rng)
        positions.append((agent.x, agent.y))
    return positions


def main():
    # Trial A — global random in some state
    random.seed(7)
    for _ in range(100):
        random.random()
    positions_a = run_trial()

    # Trial B — global random in a VERY different state
    random.seed(999)
    for _ in range(50_000):
        random.random()
    positions_b = run_trial()

    print('trial A last 5 positions:', positions_a[-5:])
    print('trial B last 5 positions:', positions_b[-5:])
    identical = positions_a == positions_b
    print(f'\nsim is deterministic under global-random pollution: {identical}')
    if not identical:
        # find the first divergent tick
        for i, (pa, pb) in enumerate(zip(positions_a, positions_b)):
            if pa != pb:
                print(f'  first divergence at tick {i}: A={pa} vs B={pb}')
                break


if __name__ == '__main__':
    main()
