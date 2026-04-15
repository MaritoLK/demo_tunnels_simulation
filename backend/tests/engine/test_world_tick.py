from app.engine.world import Tile, World
from app.engine import config


def test_tile_default_crop_state_is_none():
    t = Tile(x=0, y=0, terrain='grass')
    assert t.crop_state == 'none'
    assert t.crop_growth_ticks == 0
    assert t.crop_colony_id is None


def test_tile_accepts_crop_fields_in_constructor():
    t = Tile(x=1, y=2, terrain='grass', crop_state='growing',
             crop_growth_ticks=15, crop_colony_id=3)
    assert t.crop_state == 'growing'
    assert t.crop_growth_ticks == 15
    assert t.crop_colony_id == 3


def _world_with_growing_tile(colony_id=1):
    w = World(5, 5)
    w.tiles = [[Tile(x, y, 'grass') for x in range(5)] for y in range(5)]
    t = w.tiles[2][2]
    t.crop_state = 'growing'
    t.crop_growth_ticks = 0
    t.crop_colony_id = colony_id
    return w, t


def test_world_tick_day_increments_growth():
    w, t = _world_with_growing_tile()
    events = w.tick('day')
    assert t.crop_growth_ticks == 1
    assert events == []      # no maturation yet


def test_world_tick_non_day_does_not_grow():
    for phase in ('dawn', 'dusk', 'night'):
        w, t = _world_with_growing_tile()
        events = w.tick(phase)
        assert t.crop_growth_ticks == 0, f'grew during {phase}'
        assert events == []


def test_world_tick_matures_at_threshold():
    w, t = _world_with_growing_tile()
    t.crop_growth_ticks = config.CROP_MATURE_TICKS - 1
    events = w.tick('day')
    assert t.crop_state == 'mature'
    assert t.resource_amount == config.HARVEST_YIELD
    assert len(events) == 1
    e = events[0]
    assert e['type'] == 'crop_matured'
    assert e['data']['tile_x'] == 2
    assert e['data']['tile_y'] == 2
    assert e['data']['colony_id'] == 1


def test_world_tick_mature_tile_is_idempotent():
    w, t = _world_with_growing_tile()
    t.crop_state = 'mature'
    t.crop_growth_ticks = config.CROP_MATURE_TICKS
    events = w.tick('day')
    assert events == []
    assert t.crop_state == 'mature'
