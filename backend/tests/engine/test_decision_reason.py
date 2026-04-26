"""Per-branch Decision tests. One per branch of decide_action's priority
ladder. Each asserts (a) .action == expected, and (b) a discriminator
substring is present in .reason. Substring assertions intentionally
don't lock exact wording — reason strings evolve; action + discriminator
is the load-bearing invariant.

See docs/superpowers/specs/2026-04-23-agent-shine-design.md §Single-
source-of-truth for action + reason.
"""
from app.engine import config, needs
from app.engine.agent import Agent, decide_action
from app.engine.colony import EngineColony
from app.engine.world import Tile, World


def _grass_world(w=5, h=5):
    world = World(w, h)
    world.tiles = [
        [Tile(x=x, y=y, terrain='grass', resource_type=None, resource_amount=0)
         for x in range(w)]
        for y in range(h)
    ]
    return world


def _off_camp_colony():
    """Camp off-grid so agents are never at_camp."""
    return EngineColony(id=1, name='Test', color='#000', camp_x=99, camp_y=99,
                        food_stock=18,
                        growing_count=config.MAX_FIELDS_PER_COLONY)


def _at_camp_colony():
    """Camp at (0,0) for at-camp branch tests."""
    return EngineColony(id=1, name='Test', color='#000', camp_x=0, camp_y=0,
                        food_stock=18,
                        growing_count=config.MAX_FIELDS_PER_COLONY)


def _healthy_agent(x=2, y=2, colony_id=1):
    a = Agent('X', x, y, colony_id=colony_id)
    a.hunger = needs.NEED_MAX
    a.energy = needs.NEED_MAX
    a.social = needs.NEED_MAX
    a.health = needs.NEED_MAX
    return a


def test_critical_health_low_energy_picks_rest_with_health_and_energy_reason():
    a = _healthy_agent()
    a.health = needs.HEALTH_CRITICAL - 1
    a.energy = needs.ENERGY_CRITICAL - 1
    d = decide_action(a, _grass_world(), _off_camp_colony(), 'day')
    assert d.action == 'rest'
    assert 'health' in d.reason
    assert 'energy' in d.reason


def test_critical_health_high_energy_picks_forage_with_health_reason():
    a = _healthy_agent()
    a.health = needs.HEALTH_CRITICAL - 1
    d = decide_action(a, _grass_world(), _off_camp_colony(), 'day')
    assert d.action == 'forage'
    assert 'health' in d.reason


def test_critical_hunger_picks_forage_with_hunger_reason():
    a = _healthy_agent()
    a.hunger = needs.HUNGER_CRITICAL - 1
    d = decide_action(a, _grass_world(), _off_camp_colony(), 'day')
    assert d.action == 'forage'
    assert 'hunger' in d.reason


def test_critical_energy_picks_rest_with_energy_reason():
    a = _healthy_agent()
    a.energy = needs.ENERGY_CRITICAL - 1
    d = decide_action(a, _grass_world(), _off_camp_colony(), 'day')
    assert d.action == 'rest'
    assert 'energy' in d.reason


def test_night_phase_picks_rest_outdoors_with_night_reason():
    a = _healthy_agent()
    d = decide_action(a, _grass_world(), _off_camp_colony(), 'night')
    assert d.action == 'rest_outdoors'
    assert 'night' in d.reason


def test_at_camp_with_cargo_picks_deposit_with_cargo_reason():
    a = _healthy_agent(x=0, y=0)
    a.cargo = 3.0
    d = decide_action(a, _grass_world(), _at_camp_colony(), 'day')
    assert d.action == 'deposit'
    assert 'cargo' in d.reason


def test_at_camp_dawn_hungry_with_stock_picks_eat_camp():
    a = _healthy_agent(x=0, y=0)
    a.hunger = 60.0                # < NEED_MAX so eligible to eat
    a.ate_this_dawn = False
    d = decide_action(a, _grass_world(), _at_camp_colony(), 'dawn')
    assert d.action == 'eat_camp'
    assert 'eat' in d.reason


def test_at_camp_low_social_picks_socialise():
    a = _healthy_agent(x=0, y=0)
    a.social = needs.SOCIAL_LOW - 1
    d = decide_action(a, _grass_world(), _at_camp_colony(), 'day')
    assert d.action == 'socialise'
    assert 'social' in d.reason


def test_off_camp_low_social_picks_step_to_camp():
    a = _healthy_agent()
    a.social = needs.SOCIAL_LOW - 1
    d = decide_action(a, _grass_world(), _off_camp_colony(), 'day')
    assert d.action == 'step_to_camp'
    assert 'social' in d.reason


def test_off_camp_cargo_full_picks_step_to_camp():
    a = _healthy_agent()
    a.cargo = needs.CARRY_MAX
    d = decide_action(a, _grass_world(), _off_camp_colony(), 'day')
    assert d.action == 'step_to_camp'
    assert 'cargo' in d.reason


def test_mature_tile_picks_harvest():
    a = _healthy_agent()
    w = _grass_world()
    w.get_tile(a.x, a.y).crop_state = 'mature'
    d = decide_action(a, w, _off_camp_colony(), 'day')
    assert d.action == 'harvest'
    assert 'harvest' in d.reason or 'mature' in d.reason


def test_empty_tile_with_field_room_picks_plant():
    a = _healthy_agent()  # at (2,2)
    # Camp at (5,5) so the agent at (2,2) is off-camp BUT within the
    # PLANT_RADIUS_FROM_CAMP=4 field bubble (Chebyshev distance 3).
    # Pre-radius-rule the test used camp_x=99 to force off-camp; that
    # also put the agent miles outside the plantable area, so plant
    # would now be refused and the test would (incorrectly) read as
    # broken behaviour rather than a tightened gate.
    c = EngineColony(id=1, name='Test', color='#000', camp_x=5, camp_y=5,
                     food_stock=18, growing_count=0)
    d = decide_action(a, _grass_world(), c, 'day')
    assert d.action == 'plant'
    assert 'plant' in d.reason or 'empty' in d.reason


def test_rogue_hungry_with_cargo_picks_eat_cargo():
    a = _healthy_agent()
    a.rogue = True
    a.cargo = 2.0
    a.hunger = needs.HUNGER_MODERATE - 1
    d = decide_action(a, _grass_world(), _off_camp_colony(), 'day')
    assert d.action == 'eat_cargo'
    assert 'rogue' in d.reason or 'pouch' in d.reason


def test_tail_moderate_hunger_picks_forage():
    a = _healthy_agent()
    a.hunger = needs.HUNGER_MODERATE - 1
    d = decide_action(a, _grass_world(), _off_camp_colony(), 'day')
    assert d.action == 'forage'
    assert 'hunger' in d.reason


def test_tail_all_ok_picks_explore():
    a = _healthy_agent()
    d = decide_action(a, _grass_world(), _off_camp_colony(), 'day')
    assert d.action == 'explore'
    assert 'explore' in d.reason or 'ok' in d.reason
