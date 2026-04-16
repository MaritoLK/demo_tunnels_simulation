from app.engine.agent import Agent, tick_agent
from app.engine.colony import EngineColony
from app.engine.world import Tile, World
from app.engine import needs
import random


def _world():
    w = World(5, 5)
    w.tiles = [[Tile(x, y, 'grass') for x in range(5)] for y in range(5)]
    return w


def _colony(): return EngineColony(1, 'R', '#000', camp_x=0, camp_y=0, food_stock=18)


def test_night_phase_hunger_decays_at_half_rate():
    a_day = Agent('A', 2, 2, agent_id=1, colony_id=1)
    a_night = Agent('B', 2, 2, agent_id=2, colony_id=1)
    a_day.hunger = a_night.hunger = 80.0
    w = _world()
    rng = random.Random(1)
    tick_agent(a_day, w, [a_day], {1: _colony()}, phase='day', rng=rng)
    tick_agent(a_night, w, [a_night], {1: _colony()}, phase='night', rng=rng)
    assert 80.0 - a_day.hunger == needs.HUNGER_DECAY
    assert 80.0 - a_night.hunger == needs.HUNGER_DECAY * needs.NIGHT_HUNGER_SCALE


def test_ate_this_dawn_flag_clears_outside_dawn():
    a = Agent('A', 0, 0, agent_id=1, colony_id=1)
    a.ate_this_dawn = True
    w = _world()
    rng = random.Random(1)
    tick_agent(a, w, [a], {1: _colony()}, phase='day', rng=rng)
    assert a.ate_this_dawn is False
