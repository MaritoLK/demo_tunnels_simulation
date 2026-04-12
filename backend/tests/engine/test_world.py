"""World generation invariants. Pure Python — no app context, no DB."""
import pytest

from app.engine.world import World


def test_generate_is_deterministic_under_seed():
    a = World(8, 6); a.generate(seed=42)
    b = World(8, 6); b.generate(seed=42)
    shape_a = [[(t.terrain, t.resource_type, t.resource_amount) for t in row] for row in a.tiles]
    shape_b = [[(t.terrain, t.resource_type, t.resource_amount) for t in row] for row in b.tiles]
    assert shape_a == shape_b


def test_generate_differs_across_seeds():
    a = World(8, 6); a.generate(seed=1)
    b = World(8, 6); b.generate(seed=2)
    assert a.tiles != b.tiles


def test_world_has_at_least_one_walkable_tile():
    # §9.7: World.generate guarantees a walkable spawn point regardless of seed
    for seed in range(20):
        w = World(4, 4)
        w.generate(seed=seed)
        walkable = [t for row in w.tiles for t in row if t.is_walkable]
        assert walkable, f'seed={seed} produced zero walkable tiles'


def test_tile_coordinates_match_position():
    w = World(5, 3)
    w.generate(seed=0)
    for y, row in enumerate(w.tiles):
        for x, tile in enumerate(row):
            assert tile.x == x and tile.y == y
