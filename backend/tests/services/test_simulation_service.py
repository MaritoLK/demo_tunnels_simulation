"""Service layer: create / step / reload against a real Postgres schema."""
import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from app import db, models
from app.services import simulation_service
from app.services.exceptions import SimulationNotFoundError


def _snapshot(sim):
    return {
        'tick': sim.current_tick,
        'agents': [(a.id, a.x, a.y, a.hunger, a.alive) for a in sim.agents],
        'tiles': {(t.x, t.y): t.resource_amount for row in sim.world.tiles for t in row},
        'rng': sim.snapshot_rng_state(),
    }


def test_get_current_simulation_raises_when_nothing_persisted(db_session):
    with pytest.raises(SimulationNotFoundError):
        simulation_service.get_current_simulation()


def test_create_simulation_persists_initial_state(db_session):
    sim = simulation_service.create_simulation(
        width=5, height=5, seed=1, agent_count=2,
    )
    assert sim.current_tick == 0
    # DB rows landed in every table.
    assert db.session.query(models.WorldTile).count() == 25
    assert db.session.query(models.Agent).count() == 2
    assert db.session.query(models.SimulationState).count() == 1
    state = db.session.query(models.SimulationState).one()
    assert state.seed == 1
    assert state.rng_spawn_state is not None
    assert state.rng_tick_state is not None


def test_create_simulation_wipes_prior_state(db_session):
    simulation_service.create_simulation(width=3, height=3, seed=1, agent_count=1)
    simulation_service.create_simulation(width=4, height=4, seed=2, agent_count=2)
    # Only the second sim's rows survive.
    assert db.session.query(models.WorldTile).count() == 16
    assert db.session.query(models.Agent).count() == 2


def test_step_simulation_advances_tick_and_persists_events(db_session):
    simulation_service.create_simulation(width=6, height=6, seed=42, agent_count=2)
    events = simulation_service.step_simulation(ticks=5)
    assert events  # engine emits at least one event per alive agent per tick
    sim = simulation_service.get_current_simulation()
    assert sim.current_tick == 5
    # Events persisted.
    assert db.session.query(models.Event).count() == len(events)


def test_step_simulation_rejects_out_of_range_ticks(db_session):
    simulation_service.create_simulation(width=3, height=3, seed=1, agent_count=1)
    with pytest.raises(ValueError):
        simulation_service.step_simulation(ticks=0)
    with pytest.raises(ValueError):
        simulation_service.step_simulation(ticks=1_000_001)


def test_cold_start_reload_preserves_state_and_rng(db_session):
    # §9.20: the full reload contract. Re-run of audit/step7_reload.py
    # under pytest so CI catches reload regressions.
    sim = simulation_service.create_simulation(
        width=6, height=6, seed=42, agent_count=2,
    )
    simulation_service.step_simulation(ticks=20)
    before = _snapshot(sim)

    simulation_service._reset_cache()
    reloaded = simulation_service.get_current_simulation()
    after = _snapshot(reloaded)

    assert before == after


def test_query_events_filters_and_orders(db_session):
    simulation_service.create_simulation(width=5, height=5, seed=99, agent_count=2)
    simulation_service.step_simulation(ticks=10)

    all_events = simulation_service.query_events(limit=1000)
    assert len(all_events) >= 1

    # Ordering: tick ascending.
    ticks = [e.tick for e in all_events]
    assert ticks == sorted(ticks)

    # since_tick is exclusive.
    since5 = simulation_service.query_events(since_tick=5, limit=1000)
    assert all(e.tick > 5 for e in since5)

    # agent_id filter.
    agent_ids = {e.agent_id for e in all_events if e.agent_id is not None}
    if agent_ids:
        picked = next(iter(agent_ids))
        only = simulation_service.query_events(agent_id=picked, limit=1000)
        assert only and all(e.agent_id == picked for e in only)


def test_query_events_respects_limit(db_session):
    simulation_service.create_simulation(width=5, height=5, seed=99, agent_count=3)
    simulation_service.step_simulation(ticks=10)
    got = simulation_service.query_events(limit=5)
    assert len(got) <= 5


def test_event_fk_restricts_agent_delete(db_session):
    """DB-level invariant: events.agent_id FK is ON DELETE RESTRICT.

    This is the audit-log integrity contract from §9.19 — deleting an
    agent that still has attributed events must raise, not cascade.
    If a future migration flips this to CASCADE or SET NULL, this test
    fails before the change lands.
    """
    simulation_service.create_simulation(width=3, height=3, seed=1, agent_count=1)
    simulation_service.step_simulation(ticks=1)

    agent = db.session.query(models.Agent).first()
    # Pre-check: the agent actually has events attributed to it. Without
    # this, a regression that silently stopped writing agent_id would
    # make the RESTRICT test pass trivially.
    event_count = (
        db.session.query(models.Event)
        .filter(models.Event.agent_id == agent.id)
        .count()
    )
    assert event_count > 0

    with pytest.raises(IntegrityError) as exc_info:
        db.session.execute(sa.delete(models.Agent).where(models.Agent.id == agent.id))
        db.session.flush()
    # Pin the exact pgcode. Postgres distinguishes:
    #   23001 restrict_violation    ← RESTRICT fired
    #   23503 foreign_key_violation ← generic FK error (NO ACTION, etc.)
    # A bare `IntegrityError` match would also accept 23503, which would
    # silently pass if a future migration flipped RESTRICT → NO ACTION —
    # defeating the whole point of this test. 23001 is the RESTRICT-specific
    # SQLSTATE; asserting it documents the contract exactly.
    assert exc_info.value.orig.pgcode == '23001'
    db.session.rollback()
