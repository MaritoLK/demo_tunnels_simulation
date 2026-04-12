"""
Audit Defensive #1 — a seeded World.generate can produce zero walkable tiles,
and Simulation.spawn_agent then raises 'no walkable tiles to spawn on'.

TERRAIN_WEIGHTS gives water a 10% chance per tile. On a small grid an
unlucky seed can roll *every* tile to water. For a 1x1 world the chance
is ~10%; for 2x2 it's 10%^4 = 0.01%; for 3x3 it's 10^-9. Small but real.

Test: exhaustive seed search on a 1x1 world to find a seed that produces
a water tile (easy to hit). Call spawn_agent — observe RuntimeError under
the current generator. Apply the fix (guarantee at least one walkable
tile after generation) and observe spawn succeeds.
"""
import random

from app.engine.world import World, Tile, TERRAIN_WEIGHTS


def raw_generate(world, seed):
    """Pre-fix generator — terrain rolled per tile, no walkable invariant."""
    rng = random.Random(seed)
    terrains = list(TERRAIN_WEIGHTS.keys())
    weights = list(TERRAIN_WEIGHTS.values())
    world.tiles = []
    for y in range(world.height):
        row = []
        for x in range(world.width):
            terrain = rng.choices(terrains, weights=weights, k=1)[0]
            row.append(Tile(x, y, terrain))
        world.tiles.append(row)


def find_all_water_seed(limit=200):
    for s in range(limit):
        w = World(1, 1)
        raw_generate(w, seed=s)
        if not w.tiles[0][0].is_walkable:
            return s
    return None


def try_spawn(world):
    walkable = [
        (t.x, t.y)
        for row in world.tiles
        for t in row
        if t.is_walkable
    ]
    if not walkable:
        raise RuntimeError('no walkable tiles to spawn on')
    return walkable[0]


def main():
    seed = find_all_water_seed()
    if seed is None:
        print('could not find all-water seed in 1x1 within search limit')
        return

    print(f'seed {seed}: 1x1 world rolls to pure water under raw terrain rolling')

    w1 = World(1, 1)
    raw_generate(w1, seed=seed)
    print(f'raw generate (pre-fix behaviour):')
    print(f'  tile at (0,0) terrain={w1.tiles[0][0].terrain!r}, walkable={w1.tiles[0][0].is_walkable}')
    try:
        try_spawn(w1)
        print('  spawn SUCCEEDED (unexpected)')
    except RuntimeError as e:
        print(f'  spawn raised RuntimeError: {e}')

    w2 = World(1, 1)
    w2.generate(seed=seed)
    print(f'\nreal World.generate (post-fix), same seed:')
    print(f'  tile at (0,0) terrain={w2.tiles[0][0].terrain!r}, walkable={w2.tiles[0][0].is_walkable}')
    spawn_pos = try_spawn(w2)
    print(f'  spawn succeeded at {spawn_pos}')


if __name__ == '__main__':
    main()
