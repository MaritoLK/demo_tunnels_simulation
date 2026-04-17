"""Food tiles spawn with a random amount in [2, 10] (integer units).

Before this change, every food tile spawned with exactly 10 food —
flat, visually uniform, and the 'x2' badge was redundant since every
tile started at two servings. Random amounts give the badge something
to show and make the map feel less gridded.

Wood / stone amounts are not covered here — those still use the
fixed INITIAL_RESOURCE_AMOUNT values.
"""
from app.engine.world import World


def _generate(seed):
    w = World(60, 60)
    w.generate(seed=seed)
    return w


def test_food_tiles_have_amounts_in_2_to_10_range():
    w = _generate(seed=1)
    food_tiles = [
        t for row in w.tiles for t in row
        if t.resource_type == 'food' and t.resource_amount > 0
    ]
    assert food_tiles, 'expected some food tiles on a 60x60 generated world'
    for t in food_tiles:
        assert 2 <= t.resource_amount <= 10, (
            f'food tile ({t.x},{t.y}) has amount {t.resource_amount}; '
            'must be in [2, 10]'
        )


def test_food_tile_amounts_vary_across_map():
    # Random range → not every tile has the same amount. A flat-10 world
    # would still pass the bounds test above; this one catches that
    # regression specifically.
    w = _generate(seed=1)
    food_amounts = {
        t.resource_amount for row in w.tiles for t in row
        if t.resource_type == 'food' and t.resource_amount > 0
    }
    assert len(food_amounts) >= 3, (
        f'expected food amounts to vary across the map, got {food_amounts}'
    )
