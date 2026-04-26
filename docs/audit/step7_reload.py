"""Step 7 verification: honest cold-start reload preserves sim state + RNG trajectory.

Scenario:
  1. create_simulation(width, height, seed, agent_count) — persists initial state.
  2. step_simulation(N) — advances agents, triggers forages (dirty-tile path).
  3. Capture a reference snapshot: tick, agent fields, tile resource_amounts,
     RNG state for both sub-streams.
  4. Drop the in-memory cache (_reset_cache) to simulate a worker restart.
  5. get_current_simulation() — should lazily load_current_simulation() from DB.
  6. Compare reloaded state against reference snapshot. Must match bit-for-bit
     on observable fields AND on RNG internal state.
  7. Step both sims another M ticks and compare event streams — proves the
     RNG trajectory is preserved across the reload boundary (the §9.11
     reproducibility contract).

Fail loudly on any drift: that's the whole point of persisting RNG state
rather than re-seeding from master on reload.
"""
import sys

from app.app import create_app
from app import db
from app.services import simulation_service


def snapshot_sim(sim):
    return {
        'tick': sim.current_tick,
        'agents': [
            (a.id, a.name, a.x, a.y, a.state, a.hunger, a.energy,
             a.social, a.health, a.age, a.alive)
            for a in sim.agents
        ],
        'tiles': {
            (t.x, t.y): t.resource_amount
            for row in sim.world.tiles for t in row
        },
        'rng': sim.snapshot_rng_state(),
    }


def diff(label, a, b):
    if a == b:
        return []
    return [f'  {label}: MISMATCH\n    before: {a}\n    after:  {b}']


def main():
    app = create_app()
    with app.app_context():
        sim = simulation_service.create_simulation(
            width=8, height=8, seed=42, agent_count=3,
        )
        events_pre = simulation_service.step_simulation(ticks=30)
        before = snapshot_sim(sim)

        # Simulate worker restart: drop in-memory cache, force DB reload.
        simulation_service._reset_cache()
        reloaded = simulation_service.get_current_simulation()
        after = snapshot_sim(reloaded)

        problems = []
        problems += diff('tick',   before['tick'],   after['tick'])
        problems += diff('agents', before['agents'], after['agents'])
        problems += diff('tiles',  before['tiles'],  after['tiles'])
        problems += diff('rng',    before['rng'],    after['rng'])

        # Trajectory test: continue both sims another 20 ticks. Because the
        # reloaded sim shares the same DB row, we simulate the "second path"
        # by re-seeding a parallel engine from the same snapshot in memory.
        import copy
        parallel = copy.deepcopy(sim)  # sim is the original in-memory object
        reloaded_events = simulation_service.step_simulation(ticks=20)
        parallel_events = parallel.run(20)

        # Compare event streams ignoring agent_id ordering nondeterminism
        # (there isn't any — both loop in list order — so direct compare OK).
        key = lambda e: (e['tick'], e.get('agent_id'), e['type'], e.get('data'))
        if sorted(reloaded_events, key=key) != sorted(parallel_events, key=key):
            problems.append('  trajectory: event streams diverge after reload')

        if problems:
            print('FAIL: reload did not preserve state')
            for p in problems:
                print(p)
            sys.exit(1)

        print('PASS: cold-start reload preserves state and RNG trajectory')
        print(f'  events in initial 30-tick run : {len(events_pre)}')
        print(f'  events after reload (20 more) : {len(reloaded_events)}')
        print(f'  agents                        : {len(before["agents"])}')
        print(f'  world                         : 8x8 ({len(before["tiles"])} tiles)')


if __name__ == '__main__':
    main()
