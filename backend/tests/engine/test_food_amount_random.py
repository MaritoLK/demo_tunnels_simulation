"""Food tiles spawn with a random amount in
[FOOD_TILE_YIELD_MIN, FOOD_TILE_YIELD_MAX] (integer units).

Before any of this, every food tile spawned with exactly 10 food —
flat, visually uniform, and the 'x2' badge was redundant since every
tile started at two servings. The 2-10 range fixed that. The fog-of-
war / scarcity pass tightened the range to 1-5 so a colony can't
survive on tiles within sight of their camp; agents have to clear fog
and discover new food.

Wood / stone amounts are not covered here — those still use the
fixed INITIAL_RESOURCE_AMOUNT values.
"""
from app.engine.world import FOOD_TILE_YIELD_MAX, FOOD_TILE_YIELD_MIN, World


def _generate(seed):
    w = World(60, 60)
    w.generate(seed=seed)
    return w


def test_food_tiles_have_amounts_in_configured_range():
    w = _generate(seed=1)
    food_tiles = [
        t for row in w.tiles for t in row
        if t.resource_type == 'food' and t.resource_amount > 0
    ]
    assert food_tiles, 'expected some food tiles on a 60x60 generated world'
    for t in food_tiles:
        assert FOOD_TILE_YIELD_MIN <= t.resource_amount <= FOOD_TILE_YIELD_MAX, (
            f'food tile ({t.x},{t.y}) has amount {t.resource_amount}; '
            f'must be in [{FOOD_TILE_YIELD_MIN}, {FOOD_TILE_YIELD_MAX}]'
        )


def test_food_tile_amounts_vary_across_map():
    # Random range → not every tile has the same amount. A flat-10 world
    # would still pass the bounds test above; this one catches that
    # regression specifically. With the 1-5 range there are 5 possible
    # amounts so varying-≥3 is still a comfortable bound.
    w = _generate(seed=1)
    food_amounts = {
        t.resource_amount for row in w.tiles for t in row
        if t.resource_type == 'food' and t.resource_amount > 0
    }
    assert len(food_amounts) >= 3, (
        f'expected food amounts to vary across the map, got {food_amounts}'
    )
