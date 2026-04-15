from app.engine.agent import Agent
from app.engine.colony import EngineColony
from app.engine.world import Tile, World
from app.engine import actions, config


def _grass_world():
    w = World(5, 5)
    w.tiles = [[Tile(x, y, 'grass') for x in range(5)] for y in range(5)]
    return w


def _fresh_colony(growing=0, food=18):
    return EngineColony(id=1, name='Red', color='#e74c3c',
                        camp_x=0, camp_y=0, food_stock=food,
                        growing_count=growing)


def test_plant_converts_empty_tile_to_growing():
    w = _grass_world()
    a = Agent('A', 2, 2, agent_id=10, colony_id=1)
    c = _fresh_colony()
    event = actions.plant(a, w, c)
    tile = w.get_tile(2, 2)
    assert tile.crop_state == 'growing'
    assert tile.crop_growth_ticks == 0
    assert tile.crop_colony_id == 1
    assert c.growing_count == 1
    assert event['type'] == 'planted'
    assert event['data'] == {'tile_x': 2, 'tile_y': 2, 'colony_id': 1}


def test_plant_refuses_already_cultivated_tile():
    w = _grass_world()
    w.get_tile(2, 2).crop_state = 'growing'
    a = Agent('A', 2, 2, agent_id=10, colony_id=1)
    c = _fresh_colony(growing=1)
    event = actions.plant(a, w, c)
    assert event['type'] == 'idled'
    assert c.growing_count == 1


def test_plant_refuses_when_max_fields_reached():
    w = _grass_world()
    a = Agent('A', 2, 2, agent_id=10, colony_id=1)
    c = _fresh_colony(growing=config.MAX_FIELDS_PER_COLONY)
    event = actions.plant(a, w, c)
    assert event['type'] == 'idled'
    assert w.get_tile(2, 2).crop_state == 'none'
