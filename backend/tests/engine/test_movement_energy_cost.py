"""Each successful step costs energy.

Pre-fix: ENERGY_DECAY = 0.3/tick was the only drain. Over a 120-tick
day that's only -36, while a single night of rest_outdoors gave +75.
Energy never dipped below 70 in the 1500-tick diagnostic — the meter
was effectively decorative, never gated a decision.

Fix: every position change costs ENERGY_PER_STEP. Combined with the
constant decay, an actively foraging agent burns ~85/day, which the
night rest doesn't fully replenish — they need to rest occasionally
during day too. Idle / move_cooldown ticks pay only the constant
decay, so an agent stuck waiting for terrain doesn't get double-billed.
"""
import random

from app.engine import actions, needs
from app.engine.agent import Agent, tick_agent
from app.engine.colony import EngineColony
from app.engine.world import Tile, World


def _grass(width=20, height=20):
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


def _agent(x=10, y=10):
    a = Agent('A', x, y, agent_id=1, colony_id=1)
    a.hunger = 80.0
    a.energy = 80.0
    a.social = 80.0
    a.health = 100.0
    return a


def test_energy_per_step_is_positive():
    # Sanity: the constant must exist and exceed zero. Otherwise the
    # whole 'movement costs energy' design has no effect, just a name.
    assert needs.ENERGY_PER_STEP > 0


def test_successful_step_decrements_energy_beyond_decay():
    # Set up: agent in open grass, will explore on tick. Compare
    # energy delta vs the decay-only floor.
    a = _agent()
    pre_energy = a.energy
    pre_pos = (a.x, a.y)
    sim_world = _grass()
    colonies_by_id = {1: _colony()}
    tick_agent(a, sim_world, [a], colonies_by_id, phase='day', rng=random.Random(0))
    moved = (a.x, a.y) != pre_pos
    if moved:
        # Total drop = ENERGY_DECAY (per-tick) + ENERGY_PER_STEP (movement).
        expected = pre_energy - needs.ENERGY_DECAY - needs.ENERGY_PER_STEP
        assert abs(a.energy - expected) < 1e-6, (
            f'expected energy {expected}, got {a.energy} '
            f'(pre={pre_energy}, decay={needs.ENERGY_DECAY}, '
            f'step={needs.ENERGY_PER_STEP})'
        )


def test_idle_tick_does_not_charge_step_cost():
    # No-op tick: agent fully sated and on a tile with nothing to do.
    # Force the explore branch to land on the "no fog → idle" path by
    # marking every reachable tile explored. Energy should drop only
    # by the per-tick decay, not by ENERGY_PER_STEP.
    a = _agent()
    a.x, a.y = 10, 10
    sim_world = _grass()
    colony = _colony()
    # Pre-explore the entire walkable map → BFS frontier returns no
    # target → explore returns idled. Plant won't fire (far from camp).
    for x in range(20):
        for y in range(20):
            colony.explored.add((x, y))
    pre_energy = a.energy
    pre_pos = (a.x, a.y)
    tick_agent(a, sim_world, [a], {1: colony}, phase='day', rng=random.Random(0))
    if (a.x, a.y) == pre_pos:
        # Energy lost only the constant decay — no per-step charge.
        expected = pre_energy - needs.ENERGY_DECAY
        assert abs(a.energy - expected) < 1e-6, (
            f'idle agent paid step cost: pre={pre_energy}, '
            f'post={a.energy}, expected {expected}'
        )


def test_move_cooldown_skip_does_not_charge_step_cost():
    # Mid-traversal tick: move_cooldown > 0 → tick_agent returns early
    # before decide_action runs. Position doesn't change. Energy
    # should not pay the step cost; only the per-tick decay applies.
    a = _agent()
    a.move_cooldown = 2  # mid-stone or mid-forest crossing
    sim_world = _grass()
    pre_energy = a.energy
    tick_agent(a, sim_world, [a], {1: _colony()}, phase='day', rng=random.Random(0))
    expected = pre_energy - needs.ENERGY_DECAY
    assert abs(a.energy - expected) < 1e-6, (
        f'cooldown agent paid step cost: pre={pre_energy}, '
        f'post={a.energy}'
    )
    # And cooldown ticked down.
    assert a.move_cooldown == 1


def test_energy_clamps_at_zero():
    # An agent with low energy who steps must not go below 0.
    a = _agent()
    a.energy = 0.5  # less than decay + step
    sim_world = _grass()
    pre_pos = (a.x, a.y)
    tick_agent(a, sim_world, [a], {1: _colony()}, phase='day', rng=random.Random(0))
    assert a.energy >= 0.0
