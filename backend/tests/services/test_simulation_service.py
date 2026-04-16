"""Service layer: create / step / reload against a real Postgres schema."""
import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from app import db, models
from app.services import simulation_service, mappers
from app.services.exceptions import SimulationNotFoundError
from app.engine.colony import EngineColony
from app.engine.world import Tile
from app.engine.agent import Agent


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


def test_query_events_without_cursor_returns_tail_not_head(db_session):
    """§9.32 regression guard. When `since_tick` is None, `query_events`
    must return the latest `limit` events (the tail of the stream), not
    the oldest. Pre-fix, the /world/state live feed froze on tick-0 events
    after ~50 ticks because the ASC+limit query truncated the head instead
    of the tail.
    """
    simulation_service.create_simulation(width=5, height=5, seed=1, agent_count=3)
    simulation_service.step_simulation(ticks=200)
    got = simulation_service.query_events(limit=100)
    assert len(got) == 100
    ticks = [e.tick for e in got]
    assert ticks == sorted(ticks), 'return order must stay ascending'
    # Tail semantics: max tick must be the most recent (tick=199, 0-indexed).
    # Floor at 150 rather than pinning to 199 so the test survives any future
    # per-tick-event-count fluctuation — the point is "not stuck near zero."
    assert max(ticks) >= 150, f'expected tail window; max_tick={max(ticks)}'


def test_dirty_tiles_persist_depletion_after_foraged_event(db_session):
    """§9.19 dirty-set: `foraged` events drive exactly the tile rows whose
    `resource_amount` changed. Run until at least one forage lands, then
    assert the DB row matches the engine's in-memory tile for that coord.
    Guards against regressions that rebuild the whole tile table (slow)
    or skip the update entirely (stale DB state across reloads).
    """
    sim = simulation_service.create_simulation(
        width=6, height=6, seed=42, agent_count=3,
    )
    # Starting hunger=100 with 0.5/tick decay → agents don't cross
    # HUNGER_MODERATE (50) until ~tick 100. Force-drop hunger so forage
    # fires quickly instead of stepping hundreds of ticks in a unit test.
    # sim is the cached singleton; mutating in-mem agents here is what
    # the next step_simulation call reads.
    for agent in sim.agents:
        agent.hunger = 25.0

    # Snapshot pre-forage resource amounts so the "depletion happened"
    # assertion is real, not tautological. Without this, a double-bug
    # (engine skipped depletion AND service skipped write) would leave
    # engine_tile == db_tile and pass the equality check below.
    pre_amounts = {
        (t.x, t.y): t.resource_amount
        for row in sim.world.tiles for t in row
    }

    foraged = []
    for _ in range(30):
        events = simulation_service.step_simulation(ticks=1)
        foraged = [e for e in events if e['type'] == 'foraged']
        if foraged:
            break
    assert foraged, 'expected forage events once agents were pre-hungered'

    tx, ty = foraged[0]['data']['tile_x'], foraged[0]['data']['tile_y']
    taken = foraged[0]['data']['amount_taken']
    engine_tile = sim.world.get_tile(tx, ty)
    db_tile = (
        db.session.query(models.WorldTile)
        .filter(models.WorldTile.x == tx, models.WorldTile.y == ty)
        .one()
    )
    # Engine and DB agree on the post-forage value.
    assert db_tile.resource_amount == engine_tile.resource_amount, (
        f'DB out of sync with engine at ({tx},{ty}): '
        f'db={db_tile.resource_amount} engine={engine_tile.resource_amount}'
    )
    # Depletion actually landed: pre - post == amount_taken (engine side)
    # and the DB row reflects the drop.
    assert taken > 0
    assert pre_amounts[(tx, ty)] - engine_tile.resource_amount == taken
    assert db_tile.resource_amount < pre_amounts[(tx, ty)]


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


def test_colony_model_imports_and_has_expected_columns(db_session):
    c = models.Colony(name='Red', color='#e74c3c', camp_x=3, camp_y=3, food_stock=18)
    db.session.add(c)
    db.session.flush()
    assert c.id is not None
    assert c.name == 'Red'
    assert c.food_stock == 18


def test_colony_to_row_and_back_round_trip():
    ec = EngineColony(id=None, name='Red', color='#e74c3c',
                      camp_x=3, camp_y=3, food_stock=18)
    row = mappers.colony_to_row(ec)
    assert row.name == 'Red'
    assert row.food_stock == 18
    # round-trip
    restored = mappers.row_to_colony(row)
    assert restored.name == ec.name
    assert restored.camp_x == ec.camp_x
    assert restored.food_stock == ec.food_stock


def test_tile_mapping_preserves_crop_fields():
    t = Tile(x=1, y=2, terrain='grass',
             crop_state='growing', crop_growth_ticks=15, crop_colony_id=7)
    row = mappers.tile_to_row(t)
    assert row.crop_state == 'growing'
    assert row.crop_growth_ticks == 15
    assert row.crop_colony_id == 7
    back = mappers.row_to_tile(row)
    assert back.crop_state == 'growing'
    assert back.crop_colony_id == 7


def test_agent_mapping_preserves_colony_id():
    a = Agent('A', 0, 0, agent_id=None, colony_id=3)
    row = mappers.agent_to_row(a)
    assert row.colony_id == 3
    back = mappers.row_to_agent(row)
    assert back.colony_id == 3
