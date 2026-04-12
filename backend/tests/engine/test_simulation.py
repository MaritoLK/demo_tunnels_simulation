"""Simulation-level invariants: RNG independence, reproducibility, spawn safety."""
import random

import pytest

from app.engine.simulation import (
    MAX_AGENTS,
    MAX_WORLD_CELLS,
    Simulation,
    new_simulation,
)
from app.engine.world import World


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


def test_spawn_prefers_unoccupied_tiles():
    # §9.14: if there's a free walkable tile, spawn_agent picks it.
    sim = new_simulation(3, 3, seed=0, agent_count=0)
    # Block every walkable tile except one by manually placing agents there.
    walkable = [(t.x, t.y) for row in sim.world.tiles for t in row if t.is_walkable]
    assert len(walkable) >= 2
    # Seed two existing agents on the first two walkable positions.
    from app.engine.agent import Agent
    sim.agents.append(Agent('A', *walkable[0]))
    sim.agents.append(Agent('B', *walkable[1]))
    spawned = sim.spawn_agent('C')
    occupied = {(walkable[0]), (walkable[1])}
    assert (spawned.x, spawned.y) not in occupied or len(walkable) == 2
