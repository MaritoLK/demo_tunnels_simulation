"""
Audit Bug #5 — per-agent flush in create_simulation causes N round-trips.

simulation_service.create_simulation inserts agents like this:

    for agent in sim.agents:
        row = mappers.agent_to_row(agent)
        db.session.add(row)
        db.session.flush()      # <-- per-agent flush
        agent.id = row.id

Every flush() sends an INSERT to the DB and waits for the generated id to
come back. For N agents that is N INSERT statements and N round-trips,
even though SQLAlchemy 2.x with `insertmanyvalues` can batch them all
into a single INSERT ... VALUES (...), (...), ... RETURNING id.

Test: attach a 'before_cursor_execute' listener to the engine, count the
number of INSERT statements targeting `agents`, and compare the current
per-agent-flush version vs an add_all + single-flush version.
"""
import re

from sqlalchemy import event

from app.app import create_app
from app import db, models
from app.engine.simulation import new_simulation
from app.services import mappers
from app.services.simulation_service import create_simulation as real_create_simulation


AGENTS_INSERT = re.compile(r'INSERT INTO agents\b', re.IGNORECASE)


def clear_state():
    db.session.query(models.Event).delete()
    db.session.query(models.Agent).delete()
    db.session.query(models.WorldTile).delete()
    db.session.query(models.SimulationState).delete()
    db.session.commit()


def create_sim_per_agent_flush(width, height, seed, agent_count):
    """Current implementation — one flush per agent."""
    clear_state()
    sim = new_simulation(width, height, seed=seed, agent_count=agent_count)
    tile_mappings = [mappers.tile_to_row_mapping(t) for row in sim.world.tiles for t in row]
    db.session.bulk_insert_mappings(models.WorldTile, tile_mappings)
    for agent in sim.agents:
        row = mappers.agent_to_row(agent)
        db.session.add(row)
        db.session.flush()
        agent.id = row.id
    db.session.commit()
    return sim


def create_sim_batched(width, height, seed, agent_count):
    """Fixed implementation — one flush for all agents."""
    clear_state()
    sim = new_simulation(width, height, seed=seed, agent_count=agent_count)
    tile_mappings = [mappers.tile_to_row_mapping(t) for row in sim.world.tiles for t in row]
    db.session.bulk_insert_mappings(models.WorldTile, tile_mappings)
    rows = [mappers.agent_to_row(a) for a in sim.agents]
    db.session.add_all(rows)
    db.session.flush()
    for agent, row in zip(sim.agents, rows):
        agent.id = row.id
    db.session.commit()
    return sim


def measure(fn, **kwargs):
    counts = {'agent_inserts': 0, 'statements': []}

    def before(conn, cursor, statement, parameters, context, executemany):
        if AGENTS_INSERT.search(statement):
            counts['agent_inserts'] += 1
            counts['statements'].append((statement.splitlines()[0], executemany))

    event.listen(db.engine, 'before_cursor_execute', before)
    try:
        fn(**kwargs)
    finally:
        event.remove(db.engine, 'before_cursor_execute', before)
    return counts


def main():
    app = create_app()
    with app.app_context():
        n_agents = 5
        per_agent = measure(create_sim_per_agent_flush,
                            width=8, height=8, seed=1, agent_count=n_agents)
        batched = measure(create_sim_batched,
                          width=8, height=8, seed=1, agent_count=n_agents)
        real = measure(real_create_simulation,
                       width=8, height=8, seed=1, agent_count=n_agents)

        print(f'agents created per trial: {n_agents}')
        print(f'per-agent flush (legacy):  INSERT statements = {per_agent["agent_inserts"]}')
        print(f'batched flush (fix proto): INSERT statements = {batched["agent_inserts"]}')
        print(f'real service (post-fix):   INSERT statements = {real["agent_inserts"]}')

        improvement = per_agent['agent_inserts'] - real['agent_inserts']
        print(f'\nround-trips saved by fix: {improvement}')
        print(f'real service matches fix proto: {real["agent_inserts"] == batched["agent_inserts"]}')


if __name__ == '__main__':
    main()
