from app.engine.world import Tile


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
