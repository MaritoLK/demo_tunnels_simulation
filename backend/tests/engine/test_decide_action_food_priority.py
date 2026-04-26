"""Food is precious — adjacent food triggers forage even when the
agent's own hunger is fine, as long as the pouch has room.

Pre-fix: a sated agent with cargo room walked past adjacent food and
emitted 'explore' instead — the user's "food is meant to be precious,
they should collect it on sight" report. Post-fix: the decision ladder
gains an opportunistic-forage rung between the rogue eat-from-pouch
branch and the tail explore/forage branch.

Why between, not before tile-local: harvest/plant on the agent's own
tile still wins (mature crops pay more than wild food, and planting
is a colony investment). Cargo-full step-to-camp also still wins —
no point grabbing food the agent can't carry home.
"""
from app.engine.agent import Agent, decide_action
from app.engine.colony import EngineColony
from app.engine import needs
from app.engine.world import Tile, World


def _grass_world():
    w = World(5, 5)
    w.tiles = [[Tile(x, y, 'grass') for x in range(5)] for y in range(5)]
    return w


def _colony():
    return EngineColony(id=1, name='Red', color='#e74c3c',
                        camp_x=0, camp_y=0, food_stock=18)


def _set_food(world, x, y, amount=5.0):
    t = world.get_tile(x, y)
    t.resource_type = 'food'
    t.resource_amount = amount


def _fresh_agent(x=2, y=2):
    # Sated on every axis — falls into the tail branch normally. Place
    # off the camp tile (camp at 0,0) so the at-camp branch doesn't fire.
    a = Agent('A', x, y, agent_id=1, colony_id=1)
    a.hunger = 80.0
    a.energy = 80.0
    a.social = 80.0
    a.health = 80.0
    return a


def test_decide_action_forages_when_food_adjacent_and_sated():
    # Sated agent, food in the adjacent tile, pouch empty. Pre-fix:
    # decide_action returned 'explore' (tail branch). Post-fix: returns
    # 'forage' so the agent grabs the food on sight.
    w = _grass_world()
    _set_food(w, 3, 2)  # tile east of agent at (2,2)
    a = _fresh_agent()
    decision = decide_action(a, w, _colony(), 'day')
    assert decision.action == 'forage', (
        f"sated agent next to food chose {decision.action!r} "
        f"({decision.reason!r}) — expected opportunistic forage"
    )


def test_decide_action_forages_when_standing_on_food_and_sated():
    # Same logic — own tile counts as adjacent. Standing on a food
    # tile while sated should still forage rather than plant or
    # explore. Plant guard already requires resource_amount==0 so
    # there's no rule conflict; this test pins that the new branch
    # is reached when own-tile is the food source.
    w = _grass_world()
    _set_food(w, 2, 2)
    a = _fresh_agent()
    decision = decide_action(a, w, _colony(), 'day')
    assert decision.action == 'forage', (
        f"got {decision.action!r} ({decision.reason!r})"
    )


def test_decide_action_skips_food_when_pouch_full():
    # Cargo at CARRY_MAX → cargo-full branch fires (#5) → step_to_camp.
    # Opportunistic forage should NOT pre-empt that — no point grabbing
    # food the agent can't carry home.
    w = _grass_world()
    _set_food(w, 3, 2)
    a = _fresh_agent()
    a.cargo = needs.CARRY_MAX
    decision = decide_action(a, w, _colony(), 'day')
    assert decision.action == 'step_to_camp'


def test_decide_action_explores_when_no_food_adjacent():
    # Sanity: the new branch must NOT fire when there's no food
    # nearby. Sated agent on grass, food two tiles away — falls
    # through to tail explore.
    w = _grass_world()
    _set_food(w, 4, 2)  # two tiles east
    a = _fresh_agent()
    # Force tile-local 'plant' guard to fail by putting a growing
    # crop on the agent's tile, so the test isolates the food branch.
    w.get_tile(2, 2).crop_state = 'growing'
    decision = decide_action(a, w, _colony(), 'day')
    assert decision.action == 'explore', (
        f"got {decision.action!r} ({decision.reason!r}) — food was "
        f"two tiles away, opportunistic forage should not fire"
    )


def test_decide_action_harvest_still_wins_over_food_adjacent():
    # Mature crop on the own tile: harvest is the explicit winner of
    # tile-local and outranks opportunistic forage. The opportunistic
    # branch sits below tile-local in the ladder.
    w = _grass_world()
    w.get_tile(2, 2).crop_state = 'mature'
    _set_food(w, 3, 2)
    a = _fresh_agent()
    decision = decide_action(a, w, _colony(), 'day')
    assert decision.action == 'harvest'
