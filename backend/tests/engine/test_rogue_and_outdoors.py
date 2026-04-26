"""Rogue state + outdoor rest + camp-gated socialise.

Design:
  * agent.rogue: bool, default False. Flipped True when social hits 0.
    One-way — no redemption arc in this iteration.
  * socialise() only refills social if both agents on own camp tile.
  * rest_outdoors action: half REST_ENERGY_RESTORE, no heal bonus.
  * Night phase: at camp → rest. Else → rest_outdoors (don't force-march home).
  * Day phase: if social < SOCIAL_LOW and not rogue → step_to_camp
    (seek social recharge). Rogue agents skip all camp-seeking.
  * Dusk: non-rogue → step_to_camp. Rogue → productive fallthrough.
"""
import random

from app.engine import actions, needs
from app.engine.agent import Agent, tick_agent, decide_action
from app.engine.colony import EngineColony
from app.engine.world import Tile, World


def _grass_world(w=6, h=6):
    world = World(w, h)
    world.tiles = [[Tile(x, y, 'grass') for x in range(w)] for y in range(h)]
    return world


def _colony(food=100, camp=(0, 0)):
    return EngineColony(1, 'R', '#000', camp_x=camp[0], camp_y=camp[1], food_stock=food)


# ─── rogue flag ───────────────────────────────────────────────────────

def test_agent_starts_non_rogue():
    a = Agent('A', 0, 0, agent_id=1, colony_id=1)
    assert a.rogue is False


def test_social_hitting_zero_flips_rogue():
    a = Agent('A', 0, 0, agent_id=1, colony_id=1)
    a.social = needs.SOCIAL_DECAY  # one decay tick away from zero
    needs.decay_needs(a)
    assert a.social == 0.0
    assert a.rogue is True


def test_social_above_zero_keeps_non_rogue():
    a = Agent('A', 0, 0, agent_id=1, colony_id=1)
    a.social = 5.0
    needs.decay_needs(a)
    assert a.social > 0.0
    assert a.rogue is False


def test_rogue_flag_is_one_way():
    """Social restore after rogue does NOT un-rogue. Once out, always out."""
    a = Agent('A', 0, 0, agent_id=1, colony_id=1)
    a.social = needs.SOCIAL_DECAY
    needs.decay_needs(a)
    assert a.rogue is True
    a.social = needs.NEED_MAX
    needs.decay_needs(a)
    assert a.rogue is True


# ─── rest_outdoors action ─────────────────────────────────────────────

def test_rest_outdoors_restores_less_energy_than_rest():
    a_home = Agent('A', 0, 0, agent_id=1, colony_id=1)
    a_outdoor = Agent('B', 3, 3, agent_id=2, colony_id=1)
    a_home.energy = a_outdoor.energy = 50.0
    actions.rest(a_home)
    actions.rest_outdoors(a_outdoor)
    home_gain = a_home.energy - 50.0
    outdoor_gain = a_outdoor.energy - 50.0
    assert outdoor_gain > 0
    assert outdoor_gain < home_gain


def test_rest_outdoors_no_heal_bonus_even_if_fed():
    a = Agent('A', 3, 3, agent_id=1, colony_id=1)
    a.hunger = needs.NEED_MAX
    a.health = 50.0
    actions.rest_outdoors(a)
    assert a.health == 50.0  # no bonus heal


# ─── camp-gated socialise ─────────────────────────────────────────────

def test_socialise_outside_camp_does_not_refill():
    c = _colony(camp=(0, 0))
    a = Agent('A', 3, 3, agent_id=1, colony_id=1)
    b = Agent('B', 3, 4, agent_id=2, colony_id=1)
    a.social = b.social = 40.0
    event = actions.socialise(a, [a, b], colony=c)
    assert a.social == 40.0
    assert b.social == 40.0
    assert event['type'] == 'idled'


def test_socialise_at_camp_refills_both():
    c = _colony(camp=(0, 0))
    a = Agent('A', 0, 0, agent_id=1, colony_id=1)
    b = Agent('B', 0, 1, agent_id=2, colony_id=1)  # adjacent to camp
    a.social = b.social = 40.0
    # Only actor on camp — current design: both must be on camp tile.
    event = actions.socialise(a, [a, b], colony=c)
    assert a.social == 40.0  # b not on camp, no refill
    # Now move b onto camp too
    b.x, b.y = 0, 0
    actions.socialise(a, [a, b], colony=c)
    assert a.social > 40.0
    assert b.social > 40.0


# ─── decide_action with rogue + social pressure ───────────────────────

def test_non_rogue_low_social_day_seeks_camp():
    c = _colony(camp=(0, 0))
    a = Agent('A', 4, 4, agent_id=1, colony_id=1)
    a.social = needs.SOCIAL_LOW - 1
    w = _grass_world()
    action = decide_action(a, w, c, phase='day').action
    assert action == 'step_to_camp'


def test_rogue_day_does_not_seek_camp():
    c = _colony(camp=(0, 0))
    a = Agent('A', 4, 4, agent_id=1, colony_id=1)
    a.rogue = True
    a.social = 5.0
    w = _grass_world()
    action = decide_action(a, w, c, phase='day').action
    assert action != 'step_to_camp'


def test_rogue_dusk_does_not_step_to_camp():
    c = _colony(camp=(0, 0))
    a = Agent('A', 4, 4, agent_id=1, colony_id=1)
    a.rogue = True
    w = _grass_world()
    action = decide_action(a, w, c, phase='dusk').action
    assert action != 'step_to_camp'


# ─── night rest behaviour ─────────────────────────────────────────────

def test_night_at_camp_rests_outdoors_post_rework():
    """Post 'remove forced returns': night is always rest_outdoors even
    on a camp tile. Previous revision branched on at-camp to pick
    'rest' (full recovery) vs 'rest_outdoors' (half recovery); the
    split pulled the whole colony back to camp every night and the
    demo showed 12 motionless pawns on 4 tiles. Uniform rest_outdoors
    keeps the rhythm but spreads agents across the map."""
    c = _colony(camp=(0, 0))
    a = Agent('A', 0, 0, agent_id=1, colony_id=1)
    w = _grass_world()
    action = decide_action(a, w, c, phase='night').action
    assert action == 'rest_outdoors'


def test_night_far_from_camp_rests_outdoors():
    c = _colony(camp=(0, 0))
    a = Agent('A', 4, 4, agent_id=1, colony_id=1)
    w = _grass_world()
    action = decide_action(a, w, c, phase='night').action
    assert action == 'rest_outdoors'


def test_rogue_night_always_rests_outdoors_even_on_camp():
    """Rogue ignores camp semantically — home doesn't exist for them."""
    c = _colony(camp=(0, 0))
    a = Agent('A', 0, 0, agent_id=1, colony_id=1)
    a.rogue = True
    w = _grass_world()
    action = decide_action(a, w, c, phase='night').action
    assert action == 'rest_outdoors'


# ─── end-to-end tick smoke ────────────────────────────────────────────

def test_tick_agent_dispatches_rest_outdoors_at_night_away_from_camp():
    a = Agent('A', 4, 4, agent_id=1, colony_id=1)
    a.energy = 30.0
    w = _grass_world()
    rng = random.Random(0)
    events = tick_agent(a, w, [a], {1: _colony(camp=(0, 0))}, phase='night', rng=rng)
    assert any(e.get('type') == 'rested_outdoors' for e in events)
    assert a.energy > 30.0
