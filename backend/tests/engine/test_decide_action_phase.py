from app.engine.agent import Agent, decide_action
from app.engine.colony import EngineColony
from app.engine.world import Tile, World
from app.engine import config, needs


def _grass_world():
    w = World(5, 5)
    w.tiles = [[Tile(x, y, 'grass') for x in range(5)] for y in range(5)]
    return w


def _colony(growing=0):
    return EngineColony(id=1, name='Red', color='#e74c3c',
                        camp_x=0, camp_y=0, food_stock=18,
                        growing_count=growing)


def _fresh_agent(x=2, y=2):
    a = Agent('A', x, y, agent_id=1, colony_id=1)
    a.hunger = 80.0
    a.energy = 80.0
    a.social = 80.0
    a.health = 80.0
    return a


def test_day_phase_harvest_wins_over_plant_when_on_mature_tile():
    w = _grass_world()
    w.get_tile(2, 2).crop_state = 'mature'
    a = _fresh_agent()
    assert decide_action(a, w, _colony(), 'day') == 'harvest'


def test_day_phase_plant_chosen_on_empty_tile():
    w = _grass_world()
    a = _fresh_agent()
    assert decide_action(a, w, _colony(), 'day') == 'plant'


def test_day_phase_growing_tile_skips_both():
    w = _grass_world()
    w.get_tile(2, 2).crop_state = 'growing'
    a = _fresh_agent()
    action = decide_action(a, w, _colony(), 'day')
    assert action in ('socialise', 'explore')


def test_hunger_critical_overrides_day_productive():
    w = _grass_world()
    a = _fresh_agent()
    a.hunger = needs.HUNGER_CRITICAL - 1
    assert decide_action(a, w, _colony(), 'day') == 'forage'


def test_max_fields_closes_plant_path():
    w = _grass_world()
    a = _fresh_agent()
    c = _colony(growing=config.MAX_FIELDS_PER_COLONY)
    action = decide_action(a, w, c, 'day')
    assert action != 'plant'


def test_dawn_phase_on_camp_returns_eat_when_hungry_and_stock():
    w = _grass_world()
    a = _fresh_agent(x=0, y=0)
    a.hunger = 60.0
    c = _colony()
    assert decide_action(a, w, c, 'dawn') == 'eat_camp'


def test_dawn_phase_off_camp_is_productive():
    """Post-rework: dawn off-camp does NOT force a march home. The agent
    drops into the day chain and works the tile (plant on an empty
    grass tile). Forcing step_to_camp made the demo feel flat — see
    'remove forced returns' change."""
    w = _grass_world()
    a = _fresh_agent(x=2, y=2)
    c = _colony()
    assert decide_action(a, w, c, 'dawn') == 'plant'


def test_dusk_phase_is_productive():
    """Post-rework: dusk no longer forces step_to_camp. Agents keep
    working until night, when they sleep where they stand."""
    w = _grass_world()
    a = _fresh_agent(x=2, y=2)
    assert decide_action(a, w, _colony(), 'dusk') == 'plant'


def test_night_phase_rests_outdoors_anywhere():
    """Post-rework: night is always rest_outdoors, even at camp. Forcing
    everyone back to camp for the rest phase turned half the day into
    idle pawns on one tile. Outdoors rest still recovers energy (at
    half rate), so the day-is-productive / night-is-sleep rhythm holds."""
    w = _grass_world()
    a = _fresh_agent(x=0, y=0)  # on camp
    assert decide_action(a, w, _colony(), 'night') == 'rest_outdoors'
    a_field = _fresh_agent(x=2, y=2)  # off camp
    assert decide_action(a_field, w, _colony(), 'night') == 'rest_outdoors'


def test_dawn_on_camp_full_hunger_is_productive():
    """Post-rework: at-camp agent at dawn who can't eat falls through
    to day-chain productivity instead of sham-resting. Planting on an
    empty camp tile is the natural choice."""
    w = _grass_world()
    a = _fresh_agent(x=0, y=0)  # on camp
    a.hunger = needs.NEED_MAX  # can't eat
    c = _colony()
    assert decide_action(a, w, c, 'dawn') == 'plant'
