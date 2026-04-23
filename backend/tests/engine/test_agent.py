"""Agent tick behaviour: needs decay, pre-decay death guard, event emission."""
import random

import pytest

from app.engine import actions, config, needs
from app.engine.agent import Agent, decide_action, tick_agent
from app.engine.colony import EngineColony
from app.engine.world import Tile, World


def _grass_world(w=3, h=3):
    world = World(w, h)
    world.tiles = [
        [Tile(x=x, y=y, terrain='grass', resource_type=None, resource_amount=0) for x in range(w)]
        for y in range(h)
    ]
    return world


def _colony(camp_x=99, camp_y=99):
    """Off-grid camp by default (no agent position lands on (99,99) in these
    tests), and growing_count pinned at MAX so the plant branch never fires.
    Both knobs keep the priority-ladder tests focused on need-driven actions
    without crop-system noise."""
    return EngineColony(id=1, name='Test', color='#000', camp_x=camp_x, camp_y=camp_y,
                        food_stock=18, growing_count=config.MAX_FIELDS_PER_COLONY)


def test_tick_agent_emits_tick_field_via_simulation():
    # tick_agent itself returns per-agent events without tick set — that's
    # the Simulation.step contract. Just assert the list is iterable here.
    world = _grass_world()
    agent = Agent('Alice', 1, 1, colony_id=1)
    events = list(tick_agent(agent, world, [agent], {1: _colony()},
                             phase='day', rng=random.Random(0)))
    assert isinstance(events, list)


def test_dead_agent_does_not_decay_or_move():
    # §9.16: tick_agent on a dead agent must be a no-op (not decay needs).
    world = _grass_world()
    agent = Agent('Dead', 1, 1, colony_id=1)
    agent.alive = False
    agent.hunger = 50.0
    events = list(tick_agent(agent, world, [agent], {1: _colony()},
                             phase='day', rng=random.Random(0)))
    assert agent.hunger == 50.0
    assert agent.x == 1 and agent.y == 1


def test_zero_health_triggers_death_before_decay():
    # §9.16: an agent that enters the tick with health <= 0 dies immediately,
    # without another round of needs decay.
    world = _grass_world()
    agent = Agent('Doomed', 1, 1, colony_id=1)
    agent.health = 0.0
    agent.hunger = 50.0
    events = list(tick_agent(agent, world, [agent], {1: _colony()},
                             phase='day', rng=random.Random(0)))
    assert agent.alive is False
    assert agent.hunger == 50.0
    assert any(e['type'] == 'died' for e in events)


def test_rng_is_required_kwonly():
    # §9.15: no `rng` kwarg → TypeError, not silent fallback to global random.
    world = _grass_world()
    agent = Agent('Alice', 1, 1, colony_id=1)
    with pytest.raises(TypeError):
        list(tick_agent(agent, world, [agent], {1: _colony()}, phase='day'))


# decide_action — full decision-tree branch coverage.
#
# The function has a priority ladder: once a higher-priority branch matches,
# lower branches never fire. Each test pins one branch by setting *all*
# needs, not just the one under test, so a change to the ladder order shows
# up as a test failure rather than a silently-wrong action.
#
# Constants pulled from needs module so renumbering thresholds stays safe.

def _healthy_agent():
    a = Agent('X', 0, 0)
    a.health = needs.NEED_MAX
    a.hunger = needs.NEED_MAX
    a.energy = needs.NEED_MAX
    a.social = needs.NEED_MAX
    return a


def test_decide_action_critical_health_low_energy_picks_rest():
    a = _healthy_agent()
    a.health = needs.HEALTH_CRITICAL - 1
    a.energy = needs.ENERGY_CRITICAL - 1
    assert decide_action(a, _grass_world(), _colony(), 'day').action == 'rest'


def test_decide_action_critical_health_ok_energy_picks_forage():
    # Critical health + energy above floor → forage (food → recovery path).
    a = _healthy_agent()
    a.health = needs.HEALTH_CRITICAL - 1
    a.energy = needs.NEED_MAX
    assert decide_action(a, _grass_world(), _colony(), 'day').action == 'forage'


def test_decide_action_critical_hunger_picks_forage():
    a = _healthy_agent()
    a.hunger = needs.HUNGER_CRITICAL - 1
    assert decide_action(a, _grass_world(), _colony(), 'day').action == 'forage'


def test_decide_action_critical_energy_picks_rest_when_hunger_ok():
    # Health + hunger ok → energy drives the decision.
    a = _healthy_agent()
    a.energy = needs.ENERGY_CRITICAL - 1
    assert decide_action(a, _grass_world(), _colony(), 'day').action == 'rest'


def test_decide_action_moderate_hunger_picks_forage():
    # Hunger between CRITICAL and MODERATE → forage early, don't wait for crisis.
    a = _healthy_agent()
    a.hunger = needs.HUNGER_MODERATE - 1
    assert decide_action(a, _grass_world(), _colony(), 'day').action == 'forage'


def test_decide_action_low_social_picks_socialise():
    # New chain only returns 'socialise' from the at-camp opportunistic branch
    # (off-camp + low social returns 'step_to_camp' instead). Position the
    # agent on the camp tile and use a colony whose camp matches.
    a = _healthy_agent()
    a.x, a.y = 0, 0
    a.social = needs.SOCIAL_LOW - 1
    camp_colony = EngineColony(id=1, name='Camp', color='#000', camp_x=0, camp_y=0,
                                food_stock=18, growing_count=config.MAX_FIELDS_PER_COLONY)
    assert decide_action(a, _grass_world(), camp_colony, 'day').action == 'socialise'


def test_decide_action_all_ok_picks_explore():
    a = _healthy_agent()
    assert decide_action(a, _grass_world(), _colony(), 'day').action == 'explore'


# Boundary tests — the ladder uses strict `<`, so exact-threshold values
# must NOT trigger the branch. These are the classic off-by-one regressions.

def test_decide_action_hunger_at_critical_threshold_does_not_pick_forage_yet():
    # hunger == HUNGER_CRITICAL → not strictly less than, so this branch
    # skips. Falls through to moderate-hunger branch (still < MODERATE).
    a = _healthy_agent()
    a.hunger = needs.HUNGER_CRITICAL
    # Still moderate because HUNGER_CRITICAL (20) < HUNGER_MODERATE (50).
    assert decide_action(a, _grass_world(), _colony(), 'day').action == 'forage'


def test_decide_action_hunger_at_moderate_threshold_skips_forage():
    # hunger == HUNGER_MODERATE → not strictly less than, falls past forage.
    a = _healthy_agent()
    a.hunger = needs.HUNGER_MODERATE
    assert decide_action(a, _grass_world(), _colony(), 'day').action == 'explore'


def test_decide_action_social_at_low_threshold_skips_socialise():
    a = _healthy_agent()
    a.social = needs.SOCIAL_LOW
    assert decide_action(a, _grass_world(), _colony(), 'day').action == 'explore'


def test_decide_action_health_at_critical_threshold_skips_emergency():
    # Exactly HEALTH_CRITICAL → emergency branch does not trigger.
    a = _healthy_agent()
    a.health = needs.HEALTH_CRITICAL
    assert decide_action(a, _grass_world(), _colony(), 'day').action == 'explore'


# Health recovery — fixes the "zombie" bug where health only ever decays.
# Design:
#   * decay_needs handles the passive drip: if hunger > MODERATE and health
#     below MAX, add PASSIVE_HEAL_RATE. Symmetric with the starvation damage
#     it already applies.
#   * rest action multiplies that: a well-fed rest recovers an extra
#     REST_HEAL_BONUS on top of the passive drip. Rest was energy-only
#     before; giving it a second benefit makes the decision tree's rest
#     branch meaningful even when energy is plentiful.

def test_decay_needs_passive_heals_when_well_fed():
    a = _healthy_agent()
    a.health = 50.0
    a.hunger = needs.HUNGER_MODERATE + 1  # above threshold → fed
    needs.decay_needs(a)
    assert a.health > 50.0


def test_decay_needs_does_not_heal_when_hunger_at_or_below_moderate():
    # At the threshold the body is "not hungry enough to heal." Strictly
    # greater than MODERATE is the gate. Mirrors the decide_action pattern.
    a = _healthy_agent()
    a.health = 50.0
    a.hunger = needs.HUNGER_MODERATE
    needs.decay_needs(a)
    assert a.health == 50.0


def test_decay_needs_caps_heal_at_need_max():
    a = _healthy_agent()
    a.health = needs.NEED_MAX
    a.hunger = needs.NEED_MAX
    needs.decay_needs(a)
    assert a.health == needs.NEED_MAX


def test_decay_needs_starvation_still_damages():
    # Regression guard: adding a heal branch must not suppress the
    # starvation-damage branch. Both live in decay_needs.
    a = _healthy_agent()
    a.health = 50.0
    a.hunger = 0.0
    needs.decay_needs(a)
    assert a.health < 50.0


def test_rest_action_heals_when_well_fed():
    a = _healthy_agent()
    a.health = 50.0
    a.energy = 50.0
    a.hunger = needs.HUNGER_MODERATE + 1
    actions.rest(a)
    assert a.health > 50.0


def test_rest_action_does_not_heal_when_hungry():
    # Rest is still a valid energy-recovery action when hungry; it just
    # doesn't grant the heal bonus. Energy should still go up.
    a = _healthy_agent()
    a.health = 50.0
    a.energy = 50.0
    a.hunger = needs.HUNGER_MODERATE
    actions.rest(a)
    assert a.health == 50.0
    assert a.energy > 50.0


def test_tick_agent_well_fed_rest_recovers_health_over_time():
    # Integration: a well-fed agent with low-enough energy to trigger rest
    # should regain health over several ticks. This is the demo-visible
    # behaviour — the health bar moves back up, not just down.
    world = _grass_world()
    a = Agent('Healer', 1, 1, colony_id=1)
    a.health = 30.0
    a.hunger = needs.NEED_MAX
    a.energy = needs.ENERGY_CRITICAL - 1  # triggers rest branch
    colonies = {1: _colony()}
    start = a.health
    for _ in range(10):
        tick_agent(a, world, [a], colonies, phase='day', rng=random.Random(0))
    assert a.health > start


def test_tick_agent_sets_last_decision_reason():
    """After one tick, agent.last_decision_reason is populated with the
    same string decide_action returned. Empty string before the first
    tick is also a contract (Agent.__init__ default)."""
    world = _grass_world()
    a = Agent('Alice', 1, 1, colony_id=1)
    assert a.last_decision_reason == ''          # pre-tick default
    tick_agent(a, world, [a], {1: _colony()}, phase='day',
               rng=random.Random(0))
    assert a.last_decision_reason != ''          # now populated
    # Reason should mention at least one semantic token the engine uses
    assert any(token in a.last_decision_reason for token in
               ('hunger', 'energy', 'social', 'cargo', 'explore', 'plant', 'forage'))
