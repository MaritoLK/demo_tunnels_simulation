"""Action-level guards: a need-action that would restore a capped need
emits idled instead of its usual event.

Prevents two flavors of sham behaviour:
  * Phase-dictated rest at dawn when agent is already topped up — the
    thing that triggered this work (user: "why do the agents start the
    day resting if their energy is full?").
  * forage() on a food tile while hunger=100: agent wastes (depletes)
    the tile for no gain. Real bug in a food-scarce demo.

Rule: if agent.<need> == NEED_MAX, the action returns {'type': 'idled',
'description': '<name> was already full on <need>'} and mutates nothing.
"""
import random

from app.engine import actions, needs
from app.engine.agent import Agent
from app.engine.colony import EngineColony
from app.engine.world import Tile, World


def _grass_world():
    w = World(4, 4)
    w.tiles = [[Tile(x, y, 'grass') for x in range(4)] for y in range(4)]
    return w


def _colony(cx=0, cy=0):
    return EngineColony(1, 'R', '#000', camp_x=cx, camp_y=cy, food_stock=50)


# ─── rest ─────────────────────────────────────────────────────────────

def test_rest_full_energy_returns_idled_no_state_change():
    a = Agent('A', 0, 0, agent_id=1, colony_id=1)
    a.energy = needs.NEED_MAX
    a.health = 50.0
    a.hunger = needs.NEED_MAX  # would otherwise qualify for heal bonus
    prior_state = a.state
    event = actions.rest(a)
    assert event['type'] == 'idled'
    assert a.state == prior_state
    assert a.health == 50.0  # no sham heal bonus


def test_rest_partial_energy_still_restores():
    """Guard is strict-equal max — partial energy still rests normally."""
    a = Agent('A', 0, 0, agent_id=1, colony_id=1)
    a.energy = 50.0
    event = actions.rest(a)
    assert event['type'] == 'rested'
    assert a.energy > 50.0


# ─── rest_outdoors ────────────────────────────────────────────────────

def test_rest_outdoors_full_energy_returns_idled():
    a = Agent('A', 2, 2, agent_id=1, colony_id=1)
    a.energy = needs.NEED_MAX
    event = actions.rest_outdoors(a)
    assert event['type'] == 'idled'
    assert a.energy == needs.NEED_MAX


def test_rest_outdoors_partial_energy_still_restores():
    a = Agent('A', 2, 2, agent_id=1, colony_id=1)
    a.energy = 50.0
    event = actions.rest_outdoors(a)
    assert event['type'] == 'rested_outdoors'
    assert a.energy > 50.0


# ─── forage ───────────────────────────────────────────────────────────

def test_forage_full_hunger_and_full_cargo_does_not_deplete_tile():
    """The food-waste bug: foraging with hunger=100 previously still
    depleted the tile (agent.hunger = min(100, ...) = no-op, but
    tile.resource_amount -= taken). Current rule is stricter: a sated
    agent can still forage to stockpile for the colony — only when
    BOTH hunger and pouch are full does the guard idle and leave the
    tile alone."""
    a = Agent('A', 0, 0, agent_id=1, colony_id=1)
    a.hunger = needs.NEED_MAX
    a.cargo = needs.CARRY_MAX
    w = _grass_world()
    food_tile = w.get_tile(0, 0)
    food_tile.resource_type = 'food'
    food_tile.resource_amount = 10.0
    rng = random.Random(0)
    event = actions.forage(a, w, rng=rng)
    assert event['type'] == 'idled'
    assert food_tile.resource_amount == 10.0


def test_forage_partial_hunger_still_depletes():
    a = Agent('A', 0, 0, agent_id=1, colony_id=1)
    a.hunger = 50.0
    w = _grass_world()
    food_tile = w.get_tile(0, 0)
    food_tile.resource_type = 'food'
    food_tile.resource_amount = 10.0
    rng = random.Random(0)
    event = actions.forage(a, w, rng=rng)
    assert event['type'] == 'foraged'
    assert food_tile.resource_amount < 10.0


# ─── socialise ────────────────────────────────────────────────────────

def test_socialise_full_social_returns_idled():
    c = _colony(cx=0, cy=0)
    a = Agent('A', 0, 0, agent_id=1, colony_id=1)
    b = Agent('B', 0, 0, agent_id=2, colony_id=1)
    a.social = needs.NEED_MAX
    b.social = 50.0
    event = actions.socialise(a, [a, b], colony=c)
    assert event['type'] == 'idled'
    # Partner's social is NOT bumped — the actor is the full one.
    assert b.social == 50.0


def test_socialise_partial_social_at_camp_still_refills():
    c = _colony(cx=0, cy=0)
    a = Agent('A', 0, 0, agent_id=1, colony_id=1)
    b = Agent('B', 0, 0, agent_id=2, colony_id=1)
    a.social = b.social = 50.0
    event = actions.socialise(a, [a, b], colony=c)
    assert event['type'] == 'socialised'
    assert a.social > 50.0
    assert b.social > 50.0


# ─── eat_camp already guarded — verify existing behaviour is preserved ──

def test_eat_camp_full_hunger_returns_idled():
    """Existing guard at actions.eat_camp — verify it still fires."""
    c = _colony(cx=0, cy=0)
    a = Agent('A', 0, 0, agent_id=1, colony_id=1)
    a.hunger = needs.NEED_MAX
    event = actions.eat_camp(a, c)
    assert event['type'] == 'idled'
