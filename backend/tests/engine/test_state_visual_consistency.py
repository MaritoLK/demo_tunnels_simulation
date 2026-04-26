"""Visual state must follow the action chosen this tick — not lag behind
the previous tick's action.

Pre-fix bug (user report 2026-04-26): "after an agent rests, if they go
back to exploring, the visual of 'rest' remains until they perform
another action". Root cause: every action's "honest-action guard" (rest
when full energy, forage when full pouch+hunger, socialise when full
social, …) returned an `idled` event WITHOUT updating `agent.state`,
and `step_to_camp` never wrote `agent.state` at all. So the rendered
state visual was a stale snapshot of whichever action *did* succeed
last, not what the agent is currently doing.

The fix is the cleanest single-source-of-truth: `execute_action` resets
`agent.state` to STATE_IDLE before dispatching, and each action that
does productive work overrides on success. Idle-guarded no-ops then
naturally read as STATE_IDLE — semantically correct, since the action
chose to do nothing this tick.

These tests pin the contract for every transition the user is likely
to see: rest → explore, rest → step_to_camp, rest_outdoors when full,
forage when full pouch+hunger, etc.
"""
import random

from app.engine import actions, needs
from app.engine.agent import Agent, execute_action
from app.engine.colony import EngineColony
from app.engine.world import Tile, World


def _grass(width=10, height=10):
    w = World(width, height)
    w.tiles = [
        [Tile(x, y, 'grass') for x in range(width)]
        for y in range(height)
    ]
    return w


def _colony():
    return EngineColony(
        id=1, name='Red', color='#e74c3c',
        camp_x=0, camp_y=0, food_stock=10,
    )


def test_rest_to_explore_updates_state_to_exploring():
    # Reproduces the user's report. Pre-fix: explore() did update state
    # on every path so this PARTICULAR transition was already correct;
    # but the surrounding bug pattern showed up on every idle-guard +
    # step_to_camp call. This test pins the headline path.
    a = Agent(name='A', x=5, y=5, agent_id=1, colony_id=1)
    a.state = actions.STATE_RESTING  # leftover from a prior rest tick
    w = _grass()
    colony = _colony()
    execute_action('explore', a, w, [a], colony, rng=random.Random(0))
    assert a.state != actions.STATE_RESTING, (
        f"state stuck at 'resting' after explore — got {a.state!r}"
    )


def test_step_to_camp_does_not_inherit_resting_state():
    # The smoking gun: step_to_camp never wrote `agent.state`. After a
    # rest cycle, the agent walks home with a 💤 floating overhead.
    a = Agent(name='A', x=5, y=5, agent_id=1, colony_id=1)
    a.state = actions.STATE_RESTING
    w = _grass()
    colony = _colony()
    execute_action('step_to_camp', a, w, [a], colony, rng=random.Random(0))
    assert a.state != actions.STATE_RESTING, (
        f"state stuck at 'resting' after step_to_camp — got {a.state!r}"
    )


def test_rest_idle_guard_clears_resting_state():
    # rest() when energy is already NEED_MAX returns 'idled' without
    # writing state. If the prior tick was 'foraging', visual lags by
    # a tick. Post-fix: state reads as STATE_IDLE — the agent isn't
    # doing anything this tick, the visual should say so.
    a = Agent(name='A', x=5, y=5, agent_id=1, colony_id=1)
    a.state = actions.STATE_FORAGING
    a.energy = needs.NEED_MAX
    w = _grass()
    colony = _colony()
    execute_action('rest', a, w, [a], colony, rng=random.Random(0))
    assert a.state != actions.STATE_FORAGING, (
        f"state stuck at 'foraging' after rest no-op — got {a.state!r}"
    )
    assert a.state == actions.STATE_IDLE


def test_rest_outdoors_idle_guard_clears_prior_state():
    # Same shape for the night-only field rest. With auto-speedup the
    # night phase blasts past quickly so the visual MUST be honest —
    # otherwise the user sees a 'foraging' label on a sleeping agent.
    a = Agent(name='A', x=5, y=5, agent_id=1, colony_id=1)
    a.state = actions.STATE_FORAGING
    a.energy = needs.NEED_MAX
    w = _grass()
    colony = _colony()
    execute_action('rest_outdoors', a, w, [a], colony, rng=random.Random(0))
    assert a.state == actions.STATE_IDLE


def test_forage_idle_guard_clears_prior_state():
    a = Agent(name='A', x=5, y=5, agent_id=1, colony_id=1)
    a.state = actions.STATE_RESTING
    a.hunger = needs.NEED_MAX
    a.cargo_food = needs.CARRY_MAX
    w = _grass()
    colony = _colony()
    execute_action('forage', a, w, [a], colony, rng=random.Random(0))
    assert a.state == actions.STATE_IDLE


def test_socialise_idle_guard_clears_prior_state():
    a = Agent(name='A', x=5, y=5, agent_id=1, colony_id=1)
    a.state = actions.STATE_RESTING
    a.social = needs.NEED_MAX
    w = _grass()
    colony = _colony()
    execute_action('socialise', a, w, [a], colony, rng=random.Random(0))
    assert a.state == actions.STATE_IDLE


def test_deposit_idle_guard_clears_prior_state():
    a = Agent(name='A', x=5, y=5, agent_id=1, colony_id=1)
    a.state = actions.STATE_RESTING
    a.cargo_food = 0  # nothing to deposit → idle path
    w = _grass()
    colony = _colony()
    execute_action('deposit', a, w, [a], colony, rng=random.Random(0))
    assert a.state == actions.STATE_IDLE


def test_plant_idle_guard_clears_prior_state():
    # Tile already has wild food → plant guard refuses → idled.
    a = Agent(name='A', x=5, y=5, agent_id=1, colony_id=1)
    a.state = actions.STATE_RESTING
    w = _grass()
    w.get_tile(5, 5).resource_type = 'food'
    w.get_tile(5, 5).resource_amount = 5.0
    colony = _colony()
    execute_action('plant', a, w, [a], colony, rng=random.Random(0))
    assert a.state == actions.STATE_IDLE


def test_successful_action_overrides_idle_default():
    # The other half of the contract: a productive action MUST set its
    # own state. Without this assertion the simplistic fix "always set
    # IDLE at the top" would silently masquerade as correct even if
    # every action stopped writing state.
    a = Agent(name='A', x=5, y=5, agent_id=1, colony_id=1)
    a.state = actions.STATE_IDLE
    a.energy = 10.0  # below ENERGY_CRITICAL → rest does real work
    w = _grass()
    colony = _colony()
    execute_action('rest', a, w, [a], colony, rng=random.Random(0))
    assert a.state == actions.STATE_RESTING, (
        f'productive rest must set state to RESTING, got {a.state!r}'
    )
