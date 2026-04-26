"""Camps must sit on walkable tiles.

User report (2026-04-26 1500-tick diagnostic): with seed=42 the
default-corner camp for colony Blue at (50,50) landed on water. Agents
spawned on a water tile, every cardinal neighbour was also water, and
they couldn't move. They burned hunger to zero and starved at tick 270
without ever taking a step (`tiles_walked == 0`).

The bug is at the world/colony seam: world generation picks terrain
biome-by-distance and corners can roll any terrain including water.
Camp positions were never reconciled against terrain, so any seed
that put water in a corner trapped the colony.

Fix: when a Simulation is constructed with explicit colonies, force
each colony's camp tile to a walkable terrain (grass, no resource,
no crop). One-shot at construction time — runtime mutation isn't
needed because camps don't move.
"""
from app.engine.colony import EngineColony
from app.engine.simulation import Simulation
from app.engine.world import Tile, World


def _world_with_water_at(camp_x, camp_y, width=10, height=10):
    """Build a world where the named camp tile rolls water but the rest
    is grass — isolates the camp-walkability fix from biome-roll
    randomness."""
    w = World(width, height)
    w.tiles = [
        [Tile(x, y, 'grass') for x in range(width)]
        for y in range(height)
    ]
    # Force the camp tile to water and surround it with water on three
    # sides so even if the agent could move it'd be trapped — pins that
    # the fix repaints the camp itself, not the neighbourhood.
    w.tiles[camp_y][camp_x].terrain = 'water'
    w.tiles[camp_y][camp_x].resource_type = None
    w.tiles[camp_y][camp_x].resource_amount = 0.0
    return w


def test_simulation_repaints_non_walkable_camp_tile_to_grass():
    world = _world_with_water_at(camp_x=5, camp_y=5)
    colony = EngineColony(
        id=1, name='Red', color='#e74c3c',
        camp_x=5, camp_y=5, food_stock=10,
    )
    Simulation(world, colonies=[colony])
    tile = world.get_tile(5, 5)
    assert tile.is_walkable, (
        f'camp tile at ({colony.camp_x},{colony.camp_y}) was not '
        f'repaired by Simulation.__init__: terrain={tile.terrain}'
    )


def test_simulation_clears_resource_on_repainted_camp_tile():
    # If the original camp tile was non-walkable AND a generation
    # quirk left a stale resource value on it, the repaint must drop
    # that resource — otherwise an agent on a "water tile that became
    # grass" would still see a phantom food/wood entry from the
    # earlier roll and forage it as if it were a real cache.
    world = _world_with_water_at(camp_x=2, camp_y=3)
    # Stale resource on the water tile (synthetic — generate() wouldn't
    # produce this, but the invariant should still hold defensively).
    world.tiles[3][2].resource_type = 'food'
    world.tiles[3][2].resource_amount = 5.0
    colony = EngineColony(
        id=1, name='Red', color='#e74c3c',
        camp_x=2, camp_y=3, food_stock=10,
    )
    Simulation(world, colonies=[colony])
    tile = world.get_tile(2, 3)
    assert tile.is_walkable
    assert tile.terrain == 'grass'
    assert tile.resource_type is None
    assert tile.resource_amount == 0.0


def test_simulation_does_not_touch_already_walkable_camp_tiles():
    # Sanity guard: if the camp tile is already grass, the repaint
    # must be a no-op. This pins that the fix doesn't blanket-overwrite
    # — relevant if a future iteration lets camps drop on forest tiles
    # intentionally.
    world = _world_with_water_at(camp_x=5, camp_y=5)
    # Restore to grass so the camp tile starts walkable.
    world.tiles[5][5].terrain = 'grass'
    colony = EngineColony(
        id=1, name='Red', color='#e74c3c',
        camp_x=5, camp_y=5, food_stock=10,
    )
    Simulation(world, colonies=[colony])
    tile = world.get_tile(5, 5)
    assert tile.terrain == 'grass'


def test_simulation_repairs_every_colony_camp_independently():
    world = _world_with_water_at(camp_x=2, camp_y=2)
    # Second water tile in another corner — both colonies trapped pre-fix.
    world.tiles[7][7].terrain = 'water'
    colonies = [
        EngineColony(id=1, name='Red',  color='#e74c3c', camp_x=2, camp_y=2, food_stock=10),
        EngineColony(id=2, name='Blue', color='#3498db', camp_x=7, camp_y=7, food_stock=10),
    ]
    Simulation(world, colonies=colonies)
    assert world.get_tile(2, 2).is_walkable
    assert world.get_tile(7, 7).is_walkable


def test_simulation_carves_walkable_neighbours_around_camp():
    # Single grass camp tile in a sea of water → agents can't step
    # anywhere from spawn (every cardinal neighbour blocked). The
    # 1500-tick diagnostic showed 4 Blue agents trapped on a 1-tile
    # island and starved at tick 270. Fix: clear the full 3x3 around
    # the camp so agents always have a path off home base.
    width, height = 10, 10
    w = World(width, height)
    w.tiles = [[Tile(x, y, 'water') for x in range(width)] for y in range(height)]
    # Camp tile alone gets to be grass before the fix runs — but
    # neighbours still water. Pre-fix: still trapped.
    colony = EngineColony(
        id=1, name='Red', color='#e74c3c',
        camp_x=5, camp_y=5, food_stock=10,
    )
    Simulation(w, colonies=[colony])
    # All 9 tiles in the 3x3 must be walkable.
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            t = w.get_tile(5 + dx, 5 + dy)
            assert t.is_walkable, (
                f'tile ({5+dx},{5+dy}) is {t.terrain} — camp 3x3 bubble '
                f'not carved, agents would starve on the island'
            )
