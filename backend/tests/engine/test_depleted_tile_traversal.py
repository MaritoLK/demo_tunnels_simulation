"""Depleted forest / stone tiles lose their movement penalty.

Forest costs 2 ticks/step and stone costs 3 because the trees / rocks
slow the agent down — once the resource is mined out the tile is
effectively bare ground and should walk like grass. The user wants
this so a chopped-out forest reads as a passable path on the map,
matching the visual swap from Tree1 → Stump2.
"""
from app.engine import actions
from app.engine.world import Tile


def test_grass_move_cost_is_one():
    t = Tile(0, 0, 'grass')
    assert actions.move_cost(t) == 1


def test_forest_with_wood_costs_two():
    t = Tile(0, 0, 'forest', resource_type='wood', resource_amount=5.0)
    assert actions.move_cost(t) == 2


def test_forest_depleted_costs_one():
    t = Tile(0, 0, 'forest', resource_type='wood', resource_amount=0.0)
    assert actions.move_cost(t) == 1, (
        'a chopped-out forest tile must walk like grass'
    )


def test_stone_with_stone_resource_costs_three():
    t = Tile(0, 0, 'stone', resource_type='stone', resource_amount=5.0)
    assert actions.move_cost(t) == 3


def test_stone_depleted_costs_one():
    t = Tile(0, 0, 'stone', resource_type='stone', resource_amount=0.0)
    assert actions.move_cost(t) == 1, (
        'a mined-out stone tile must walk like grass'
    )


def test_sand_keeps_cost_two():
    # Sand isn't a resource tile — its slowdown is the desert itself,
    # not a depletable feature. Stays at 2 regardless of resource state.
    t = Tile(0, 0, 'sand')
    assert actions.move_cost(t) == 2
