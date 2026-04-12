"""
Audit Defensive #2 — Simulation used one Random stream for both spawn
position picking and per-tick agent decisions. Adding or moving a spawn
call perturbed every subsequent tick's randomness, even for agents that
had nothing to do with the changed spawn. Sub-seeding independent
concerns (spawn vs tick) makes each stream independently reproducible.

Test: two trials with identical master seed.
  Trial A: spawn 1 agent (Alice), run 10 ticks.
  Trial B: spawn 1 agent (Alice), spawn + immediately remove 1 agent
           (Bob), run 10 ticks.
Record Alice's (x, y) trajectory in each trial.

Under a shared-RNG design, Bob's spawn consumes one rng roll, shifting
every subsequent tick roll — Alice's trajectories differ.
Under the fix (separate rng_spawn / rng_tick), Alice's trajectories are
byte-identical.

This repro runs both designs side-by-side:
  * LegacySim  — local inline class, single shared self.rng (pre-fix shape)
  * Simulation — real post-fix class with rng_spawn / rng_tick split
"""
import random

from app.engine.simulation import Simulation
from app.engine.world import World
from app.engine.agent import Agent, tick_agent


MASTER_SEED = 123


class LegacySim:
    """Pre-fix shape: single self.rng shared across spawn + tick."""
    def __init__(self, world, seed=None):
        self.world = world
        self.agents = []
        self.rng = random.Random(seed)

    def spawn_agent(self, name):
        walkable = [
            (t.x, t.y)
            for row in self.world.tiles
            for t in row
            if t.is_walkable
        ]
        x, y = self.rng.choice(walkable)
        a = Agent(name, x, y)
        self.agents.append(a)
        return a


def fresh_world():
    w = World(8, 8)
    w.generate(seed=MASTER_SEED)
    return w


def alice_path_legacy(extra_spawn):
    sim = LegacySim(fresh_world(), seed=MASTER_SEED)
    sim.spawn_agent('Alice')
    if extra_spawn:
        sim.spawn_agent('Bob')
        sim.agents.pop()
    alice = sim.agents[0]
    path = []
    for _ in range(10):
        tick_agent(alice, sim.world, sim.agents, rng=sim.rng)
        path.append((alice.x, alice.y))
    return path


def alice_path_real(extra_spawn):
    sim = Simulation(fresh_world(), seed=MASTER_SEED)
    sim.spawn_agent('Alice')
    if extra_spawn:
        sim.spawn_agent('Bob')
        sim.agents.pop()
    alice = sim.agents[0]
    path = []
    for _ in range(10):
        tick_agent(alice, sim.world, sim.agents, rng=sim.rng_tick)
        path.append((alice.x, alice.y))
    return path


def report(label, a, b):
    identical = a == b
    print(f'{label}')
    print(f'  no extra spawn : {a}')
    print(f'  + unused Bob   : {b}')
    print(f'  paths identical? {identical}')
    if not identical:
        first = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), None)
        print(f'  first divergence at tick {first}: A={a[first]} B={b[first]}')
    print()


def main():
    report(
        'Legacy design (shared self.rng):',
        alice_path_legacy(extra_spawn=False),
        alice_path_legacy(extra_spawn=True),
    )
    report(
        'Post-fix Simulation (rng_spawn + rng_tick):',
        alice_path_real(extra_spawn=False),
        alice_path_real(extra_spawn=True),
    )


if __name__ == '__main__':
    main()
