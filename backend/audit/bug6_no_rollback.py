"""
Audit Bug #6 — create_simulation has no try/except; a failure mid-write leaves
the SQLAlchemy session in an error-state transaction.

Timeline of a failure under the pre-fix code:
  1. Deletes for Event/Agent/WorldTile/SimulationState are issued and flushed.
     At this point the transaction has uncommitted DELETEs pending.
  2. An error during any later step (bulk_insert_mappings, flush, or commit)
     raises out of create_simulation without a rollback.
  3. The SQLAlchemy session is now in PendingRollbackError state. Any
     subsequent query on the same session raises instead of returning data.
  4. Outside a Flask request (e.g., a CLI job, a worker), there is no
     request-teardown hook to rollback the session — the session stays
     broken until the process dies.

Test: seed the DB with a clean simulation so there's known state. Install a
listener that raises on the first INSERT INTO world_tiles, simulating a
failure mid-operation. Call the pre-fix version — confirm the next query
raises. Call the post-fix version (try/except/rollback) — confirm the next
query succeeds and the original rows are intact.
"""
import re

from sqlalchemy import event
from sqlalchemy.exc import PendingRollbackError

from app.app import create_app
from app import db, models
from app.engine.simulation import new_simulation
from app.services import mappers
from app.services.simulation_service import create_simulation as real_create_simulation


WORLD_TILES_INSERT = re.compile(r'INSERT INTO world_tiles\b', re.IGNORECASE)


class InjectedFailure(RuntimeError):
    pass


def create_sim_no_rollback(width, height, seed, agent_count):
    """Pre-fix copy: no try/except. Matches the shape of the old code path."""
    db.session.query(models.Event).delete()
    db.session.query(models.Agent).delete()
    db.session.query(models.WorldTile).delete()
    db.session.query(models.SimulationState).delete()
    db.session.flush()

    sim = new_simulation(width, height, seed=seed, agent_count=agent_count)

    tile_mappings = [mappers.tile_to_row_mapping(t) for row in sim.world.tiles for t in row]
    db.session.bulk_insert_mappings(models.WorldTile, tile_mappings)

    agent_rows = [mappers.agent_to_row(a) for a in sim.agents]
    db.session.add_all(agent_rows)
    db.session.flush()
    for agent, row in zip(sim.agents, agent_rows):
        agent.id = row.id

    db.session.add(models.SimulationState(
        current_tick=sim.current_tick, running=False, speed=1.0,
        world_width=width, world_height=height,
    ))
    db.session.commit()
    return sim


def create_sim_with_rollback(width, height, seed, agent_count):
    """Post-fix candidate: try/except + explicit rollback."""
    try:
        db.session.query(models.Event).delete()
        db.session.query(models.Agent).delete()
        db.session.query(models.WorldTile).delete()
        db.session.query(models.SimulationState).delete()
        db.session.flush()

        sim = new_simulation(width, height, seed=seed, agent_count=agent_count)

        tile_mappings = [mappers.tile_to_row_mapping(t) for row in sim.world.tiles for t in row]
        db.session.bulk_insert_mappings(models.WorldTile, tile_mappings)

        agent_rows = [mappers.agent_to_row(a) for a in sim.agents]
        db.session.add_all(agent_rows)
        db.session.flush()
        for agent, row in zip(sim.agents, agent_rows):
            agent.id = row.id

        db.session.add(models.SimulationState(
            current_tick=sim.current_tick, running=False, speed=1.0,
            world_width=width, world_height=height,
        ))
        db.session.commit()
        return sim
    except Exception:
        db.session.rollback()
        raise


def seed_initial_state():
    real_create_simulation(width=4, height=4, seed=1, agent_count=3)


def agent_count_or_error():
    try:
        n = db.session.query(models.Agent).count()
        return ('ok', n)
    except PendingRollbackError as e:
        return ('PendingRollbackError', str(e).splitlines()[0])
    except Exception as e:
        return (type(e).__name__, str(e).splitlines()[0])


def trial(label, broken_fn):
    print(f'--- trial: {label} ---')
    seed_initial_state()
    before = db.session.query(models.Agent).count()
    print(f'  initial agent count: {before}')

    raised_once = {'done': False}

    def inject(conn, cursor, statement, parameters, context, executemany):
        if raised_once['done']:
            return
        if WORLD_TILES_INSERT.search(statement):
            raised_once['done'] = True
            raise InjectedFailure('simulated DB failure during bulk_insert_mappings')

    event.listen(db.engine, 'before_cursor_execute', inject)
    try:
        try:
            broken_fn(width=4, height=4, seed=2, agent_count=5)
            print('  create_simulation returned normally — unexpected')
        except InjectedFailure:
            print('  create_simulation raised InjectedFailure (expected)')
        except Exception as e:
            print(f'  create_simulation raised {type(e).__name__}: {str(e).splitlines()[0]}')
    finally:
        event.remove(db.engine, 'before_cursor_execute', inject)

    status, payload = agent_count_or_error()
    if status == 'ok':
        print(f'  post-failure query OK, agent count = {payload}')
    else:
        print(f'  post-failure query FAILED: {status}: {payload}')

    db.session.rollback()
    print()
    return status, payload


def main():
    app = create_app()
    with app.app_context():
        pre = trial('no try/except (pre-fix copy)', create_sim_no_rollback)
        post = trial('try/except + rollback (post-fix copy)', create_sim_with_rollback)
        real = trial('real service (post-fix applied)', real_create_simulation)

        print('summary:')
        print(f'  pre-fix copy:  post-failure query -> {pre[0]}')
        print(f'  post-fix copy: post-failure query -> {post[0]}')
        print(f'  real service:  post-failure query -> {real[0]}')
        print(f'  real service matches post-fix copy: {real[0] == post[0]}')


if __name__ == '__main__':
    main()
