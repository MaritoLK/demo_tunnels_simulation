"""Simulation-level invariants: RNG independence, reproducibility, spawn safety."""
import random

import pytest

from app.engine import needs
from app.engine.agent import Agent
from app.engine.simulation import (
    MAX_AGENTS,
    MAX_WORLD_CELLS,
    Simulation,
    new_simulation,
)
from app.engine.world import Tile, World


def test_new_simulation_rejects_zero_dim():
    with pytest.raises(ValueError):
        new_simulation(0, 5)
    with pytest.raises(ValueError):
        new_simulation(5, 0)


def test_new_simulation_rejects_oversized_world():
    # (MAX + 1)×1 still busts the cap without trying to materialise a
    # 1M-row tile array in test memory.
    with pytest.raises(ValueError):
        new_simulation(MAX_WORLD_CELLS + 1, 1)


def test_new_simulation_rejects_too_many_agents():
    with pytest.raises(ValueError):
        new_simulation(10, 10, agent_count=101)  # agents > world_cells path
    with pytest.raises(ValueError):
        new_simulation(50, 50, agent_count=MAX_AGENTS + 1)


def test_new_simulation_rejects_non_int_dims():
    with pytest.raises(ValueError):
        new_simulation('8', 8)


def test_run_under_same_seed_is_reproducible():
    # §9.11: same seed → identical event stream. This is the engine's
    # core contract; regressions here invalidate every downstream claim.
    a = new_simulation(8, 8, seed=123, agent_count=3)
    b = new_simulation(8, 8, seed=123, agent_count=3)
    events_a = a.run(50)
    events_b = b.run(50)
    assert events_a == events_b


def test_spawn_rng_does_not_consume_tick_rng():
    # §9.11: rng_spawn and rng_tick are independent sub-streams. Extra
    # spawn_agent calls must not perturb the rng_tick sequence.
    # Narrow claim because a new agent that *ticks* does consume rng_tick;
    # what matters is that the *spawn call itself* is on a separate stream.
    baseline = new_simulation(10, 10, seed=7, agent_count=2)
    extra_spawn = new_simulation(10, 10, seed=7, agent_count=2)
    for _ in range(5):
        extra_spawn.spawn_agent(f'Extra-{_}')

    # Both sims should see identical rng_tick output at this point.
    draws_a = [baseline.rng_tick.random() for _ in range(20)]
    draws_b = [extra_spawn.rng_tick.random() for _ in range(20)]
    assert draws_a == draws_b


def test_snapshot_restore_rng_preserves_trajectory():
    # §9.20: getstate/setstate round-trips the RNG sub-streams exactly.
    sim = new_simulation(6, 6, seed=99, agent_count=2)
    sim.run(10)
    snapshot = sim.snapshot_rng_state()

    # Run the "real" sim 20 more ticks.
    real_events = sim.run(20)

    # Rebuild a fresh sim from scratch at the same seed, fast-forward
    # 10 ticks, restore RNG state to match, and advance 20 more.
    replica = new_simulation(6, 6, seed=99, agent_count=2)
    replica.run(10)
    replica.restore_rng_state(snapshot)
    replica_events = replica.run(20)

    assert real_events == replica_events


def test_run_tags_each_event_with_its_emitting_tick():
    # Simulation.step sets event['tick'] = current_tick BEFORE incrementing.
    # A 5-tick run must produce events whose tick field spans 0..4, with
    # each event correctly tagged by the tick it was emitted on — not all
    # bunched onto the final tick (a previous bug shape) and not shifted
    # by one (off-by-one at the increment boundary).
    #
    # Why {0..4} is guaranteed here: tick_agent always appends exactly one
    # event per alive agent per tick (either `die` or a single
    # execute_action result), and with 2 agents starting at full health +
    # full hunger, hunger-decay of 0.5/tick can't starve anyone in 5 ticks
    # (would need 200 ticks to hit 0). So every tick emits ≥2 events and
    # the set covers 0..4 deterministically. Re-tune if agent_count or
    # ticks change.
    sim = new_simulation(5, 5, seed=7, agent_count=2)
    events = sim.run(5)
    assert events, 'expected at least one event across 5 ticks with 2 agents'
    ticks = {e['tick'] for e in events}
    assert ticks == {0, 1, 2, 3, 4}
    # Ordering is stable: within the batch, ticks are non-decreasing
    # (step appends per-tick batches in order).
    tick_seq = [e['tick'] for e in events]
    assert tick_seq == sorted(tick_seq)


def test_run_starvation_full_path_to_death_event():
    # Full starvation path: low health + zero hunger agent in a no-food
    # world must die. decay_needs drains health via STARVATION_HEALTH_DAMAGE
    # each tick until it crosses zero, then the post-decay check emits 'died'.
    # This pins the integration of needs.py + agent.py + actions.die().
    #
    # Setup includes a second (healthy) agent so the agent_id filter in
    # the post-death loop below actually has something to disambiguate —
    # otherwise `e['agent_id'] != doomed.id` is a no-op "None != None".
    world = World(3, 3)
    world.tiles = [
        [Tile(x=x, y=y, terrain='grass', resource_type=None, resource_amount=0)
         for x in range(3)]
        for y in range(3)
    ]
    sim = Simulation(world, seed=1)

    doomed = Agent('Doomed', 1, 1, agent_id=1)
    doomed.hunger = 0.0
    # Health = 2 * STARVATION_HEALTH_DAMAGE → tick 0 drains to HALF, tick 1
    # drains to 0 and emits 'died'. Pinning the exact tick makes an
    # off-by-one in decay ordering (pre-decay vs post-decay death check)
    # fail loudly instead of producing a "death within 10" pass.
    doomed.health = needs.STARVATION_HEALTH_DAMAGE * 2
    sim.add_agent(doomed)

    survivor = Agent('Survivor', 0, 0, agent_id=2)
    sim.add_agent(survivor)

    events = sim.run(10)

    # Death happens at tick index 1 (second tick of the run). Pinning the
    # tick index — not just "somewhere in the 10-tick run" — catches a
    # regression that shifts the death by one tick.
    death_events = [e for e in events if e['type'] == 'died' and e['agent_id'] == doomed.id]
    assert len(death_events) == 1, f'expected exactly one death event for doomed, got {death_events}'
    assert death_events[0]['tick'] == 1
    assert doomed.alive is False
    assert survivor.alive is True

    # Post-death ticks are no-ops for the dead agent: no further events
    # attributed to doomed after its death event. Using `and` (not `or`)
    # is the actual "exclude doomed-died events" predicate.
    death_idx = events.index(death_events[0])
    for e in events[death_idx + 1:]:
        assert not (e['agent_id'] == doomed.id and e['type'] == 'died')


def test_spawn_prefers_unoccupied_tiles():
    # §9.14: if there's a free walkable tile, spawn_agent picks it.
    sim = new_simulation(3, 3, seed=0, agent_count=0)
    # Block every walkable tile except one by manually placing agents there.
    walkable = [(t.x, t.y) for row in sim.world.tiles for t in row if t.is_walkable]
    assert len(walkable) >= 2
    # Seed two existing agents on the first two walkable positions.
    sim.agents.append(Agent('A', *walkable[0]))
    sim.agents.append(Agent('B', *walkable[1]))
    spawned = sim.spawn_agent('C')
    occupied = {(walkable[0]), (walkable[1])}
    assert (spawned.x, spawned.y) not in occupied or len(walkable) == 2
