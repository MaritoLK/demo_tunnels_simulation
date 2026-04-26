"""Crop fields cluster around the colony's camp.

User report 2026-04-26: 'crops are all over the place', and visually
agents could plant ON the camp tile, putting a crop dot under the
house sprite. Two-part fix:

  1. Plant gate refuses when the tile IS the colony's camp — keeps
     the home tile clean for the house sprite + the deposit / eat /
     socialise actions that fire there.
  2. Plant gate refuses when the tile sits outside Chebyshev radius
     PLANT_RADIUS_FROM_CAMP of the colony's camp — agents can no
     longer drop a crop in the middle of the wilderness; fields read
     as a coherent 'tilled area near home' instead of speckle.

Both rules live in one helper `is_plantable(tile, colony)` consulted
by decide_action AND the plant action — so the ladder gate and the
action gate can't drift (CLAUDE.md design principle: single source
of truth for paired logic).
"""
from app.engine import actions, config, needs
from app.engine.agent import Agent, decide_action
from app.engine.colony import EngineColony
from app.engine.world import Tile, World


def _grass(width=20, height=20):
    w = World(width, height)
    w.tiles = [
        [Tile(x, y, 'grass') for x in range(width)]
        for y in range(height)
    ]
    return w


def _colony(camp_x=10, camp_y=10):
    return EngineColony(
        id=1, name='Red', color='#e74c3c',
        camp_x=camp_x, camp_y=camp_y, food_stock=10,
    )


def _fresh_agent(x, y):
    a = Agent('A', x, y, agent_id=1, colony_id=1)
    a.hunger = 80.0
    a.energy = 80.0
    a.social = 80.0
    a.health = 100.0
    return a


# ---- is_plantable contract ------------------------------------------------


def test_is_plantable_rejects_camp_tile():
    w = _grass()
    colony = _colony(camp_x=10, camp_y=10)
    camp_tile = w.get_tile(10, 10)
    assert not actions.is_plantable(camp_tile, colony), (
        'camp tile must never be plantable — house sprite renders here'
    )


def test_is_plantable_rejects_tile_outside_field_radius():
    w = _grass()
    colony = _colony(camp_x=10, camp_y=10)
    far = w.get_tile(10 + config.PLANT_RADIUS_FROM_CAMP + 1, 10)
    assert not actions.is_plantable(far, colony)


def test_is_plantable_accepts_tile_at_field_edge():
    w = _grass()
    colony = _colony(camp_x=10, camp_y=10)
    edge = w.get_tile(10 + config.PLANT_RADIUS_FROM_CAMP, 10)
    assert actions.is_plantable(edge, colony)


def test_is_plantable_rejects_growing_or_resourced_tile():
    # Pre-existing rules still apply: no double-plant, no plant over
    # a wild food cache. Pinned so the new radius gate doesn't accidentally
    # short-circuit the older guards.
    w = _grass()
    colony = _colony(camp_x=10, camp_y=10)
    # Empty + within radius → ok
    near = w.get_tile(11, 11)
    assert actions.is_plantable(near, colony)
    # Add a growing crop → no
    near.crop_state = 'growing'
    assert not actions.is_plantable(near, colony)
    near.crop_state = 'none'
    # Add a wild food → no
    near.resource_type = 'food'
    near.resource_amount = 5.0
    assert not actions.is_plantable(near, colony)


def test_is_plantable_rejects_when_field_cap_reached():
    w = _grass()
    colony = _colony(camp_x=10, camp_y=10)
    colony.growing_count = config.MAX_FIELDS_PER_COLONY
    near = w.get_tile(11, 11)
    assert not actions.is_plantable(near, colony)


# ---- plant action gate ----------------------------------------------------


def test_plant_action_idles_on_camp_tile():
    a = _fresh_agent(10, 10)
    w = _grass()
    colony = _colony(camp_x=10, camp_y=10)
    ev = actions.plant(a, w, colony)
    assert ev['type'] == 'idled'
    # No crop landed on the camp tile.
    assert w.get_tile(10, 10).crop_state == 'none'


def test_plant_action_idles_far_from_camp():
    far_x = 10 + config.PLANT_RADIUS_FROM_CAMP + 2
    a = _fresh_agent(far_x, 10)
    w = _grass()
    colony = _colony(camp_x=10, camp_y=10)
    ev = actions.plant(a, w, colony)
    assert ev['type'] == 'idled'
    assert w.get_tile(far_x, 10).crop_state == 'none'


def test_plant_action_succeeds_within_field_radius():
    a = _fresh_agent(11, 11)
    w = _grass()
    colony = _colony(camp_x=10, camp_y=10)
    ev = actions.plant(a, w, colony)
    assert ev['type'] == 'planted'
    assert w.get_tile(11, 11).crop_state == 'growing'


# ---- decide_action consistency with is_plantable -------------------------


def test_decide_action_does_not_pick_plant_on_camp_tile():
    a = _fresh_agent(10, 10)
    w = _grass()
    colony = _colony(camp_x=10, camp_y=10)
    decision = decide_action(a, w, colony, 'day')
    # Camp tile + at_camp + nothing else to do → social would fire if
    # social-low, deposit if cargo>0, etc. Without those, we skip
    # plant (camp tile) and fall through to tail. Just assert plant
    # is not the choice.
    assert decision.action != 'plant', (
        f"decide_action picked 'plant' on camp tile — got "
        f"{decision.action!r} ({decision.reason!r})"
    )


def test_decide_action_does_not_pick_plant_far_from_camp():
    far_x = 10 + config.PLANT_RADIUS_FROM_CAMP + 2
    a = _fresh_agent(far_x, 10)
    w = _grass()
    colony = _colony(camp_x=10, camp_y=10)
    decision = decide_action(a, w, colony, 'day')
    assert decision.action != 'plant', (
        f"decide_action picked 'plant' beyond field radius — got "
        f"{decision.action!r} ({decision.reason!r})"
    )
    # The default tail explore should fire here — sated agent, nothing
    # else to do.
    assert decision.action == 'explore'


def test_decide_action_picks_plant_on_eligible_field_tile():
    a = _fresh_agent(11, 11)
    w = _grass()
    colony = _colony(camp_x=10, camp_y=10)
    decision = decide_action(a, w, colony, 'day')
    assert decision.action == 'plant'
