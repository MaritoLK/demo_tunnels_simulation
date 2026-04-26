"""
Audit Correctness #3 — spawn_agent picked a walkable tile uniformly at
random with no occupancy check. Multiple agents routinely stacked on the
same tile, especially on small worlds. Combined with bug #10, stacked
agents used to be mutually invisible to socialise() and stayed socially
starved forever.

Test: 2x1 all-grass world, spawn 2 agents, repeat for 200 seeds.
  Pre-fix: collisions occur (both agents share a tile) roughly half
           the trials — P(collision) = 1/2 for uniform choice over
           2 tiles.
  Post-fix: spawn picks an unoccupied walkable tile when one exists,
           so 0 collisions on this setup. Falls back to any walkable
           tile only when every walkable is already occupied.
"""
from app.engine.simulation import Simulation
from app.engine.world import World, Tile


def two_tile_world():
    w = World(2, 1)
    w.tiles = [[Tile(0, 0, 'grass'), Tile(1, 0, 'grass')]]
    return w


def legacy_spawn(sim, name):
    """Pre-fix: uniform random pick, no occupancy check."""
    walkable = [
        (t.x, t.y)
        for row in sim.world.tiles
        for t in row
        if t.is_walkable
    ]
    x, y = sim.rng_spawn.choice(walkable)
    from app.engine.agent import Agent
    agent = Agent(name, x, y)
    sim.agents.append(agent)
    return agent


def count_collisions(use_legacy, trials=200):
    hits = 0
    for seed in range(trials):
        sim = Simulation(two_tile_world(), seed=seed)
        if use_legacy:
            legacy_spawn(sim, 'Alice')
            legacy_spawn(sim, 'Bob')
        else:
            sim.spawn_agent('Alice')
            sim.spawn_agent('Bob')
        a, b = sim.agents
        if (a.x, a.y) == (b.x, b.y):
            hits += 1
    return hits


def main():
    trials = 200
    print(f'2x1 grass world, 2 agents, {trials} seeds.\n')
    print(f'Pre-fix  (uniform choice)   : {count_collisions(use_legacy=True, trials=trials)} / {trials} collisions')
    print(f'Post-fix (prefer unoccupied): {count_collisions(use_legacy=False, trials=trials)} / {trials} collisions')


if __name__ == '__main__':
    main()
