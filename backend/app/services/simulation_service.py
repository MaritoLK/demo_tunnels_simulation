"""Service boundary between the pure engine and the Flask/DB world.

Ownership:
  * `create_simulation` — wipe + seed a fresh sim; persist full initial state.
  * `step_simulation`   — advance N ticks in memory, persist deltas.
  * `get_current_simulation` — in-memory cache, lazily rehydrated from DB
                               on first call after process boot.
  * `load_current_simulation` — explicit DB → engine rehydration.

The in-memory `_current_sim` survives across requests within one worker
(single-worker deployment constraint, see STUDY_NOTES §8.1). Across worker
restarts the state is re-loaded from DB on demand — the `snapshot_rng_state`
bridge in `engine.simulation` preserves the §9.11 reproducibility contract
across process boundaries.
"""
from sqlalchemy import tuple_

from app import db, models
from app.engine.simulation import Simulation, new_simulation
from app.engine import config as engine_config, cycle
from app.engine.colony import EngineColony

from . import mappers
from .exceptions import SimulationNotFoundError


_current_sim = None

# One request cannot hold a transaction open for a million ticks. Cap the
# per-call advance at MAX_TICKS_PER_STEP; the route layer rejects larger
# values with 400 before they reach the service, this is defence-in-depth.
MAX_TICKS_PER_STEP = 1000


def get_current_simulation():
    """Return the in-memory sim, rehydrating from DB if needed.

    Raises SimulationNotFoundError when no sim is persisted either.
    """
    global _current_sim
    if _current_sim is None:
        _current_sim = load_current_simulation()
    return _current_sim


def get_simulation_control():
    """Return the user-controllable sim flags: {running, speed}.

    Lives on SimulationState (not the in-memory Simulation) because these
    are orchestration knobs — the background tick thread reads speed to
    set its sleep, routes mutate running to start/stop the loop. Keeping
    them DB-backed means a worker restart picks them up correctly; the
    thread doesn't have to own the source of truth. See §9.27.
    """
    state = db.session.query(models.SimulationState).one_or_none()
    if state is None:
        raise SimulationNotFoundError('no simulation has been created')
    return {'running': state.running, 'speed': state.speed}


MIN_SPEED = 0.1
MAX_SPEED = 20.0


def update_simulation_control(*, running=None, speed=None):
    """Partial update of the user-controllable flags. Returns the new state.

    `None` means "don't touch this field" — partial PATCH semantics. Enforces
    speed bounds here so the service is a trust boundary independent of the
    route layer (routes do the shape validation, service defends invariants
    even against a bad internal caller, e.g. a future CLI tool).
    """
    if speed is not None:
        if not isinstance(speed, (int, float)) or isinstance(speed, bool):
            raise ValueError(f'speed must be a number, got {speed!r}')
        if speed < MIN_SPEED or speed > MAX_SPEED:
            raise ValueError(
                f'speed={speed} out of range [{MIN_SPEED}, {MAX_SPEED}]'
            )
    if running is not None and not isinstance(running, bool):
        raise ValueError(f'running must be bool, got {running!r}')

    state = db.session.query(models.SimulationState).one_or_none()
    if state is None:
        raise SimulationNotFoundError('no simulation has been created')
    if running is not None:
        state.running = running
    if speed is not None:
        state.speed = speed
    db.session.commit()
    return {'running': state.running, 'speed': state.speed}


def _reset_cache():
    """For tests and reload paths — clear the module-level cache."""
    global _current_sim
    _current_sim = None


DEFAULT_COLONY_PALETTE = [
    ('Red',    '#e74c3c'),
    ('Blue',   '#3498db'),
    ('Purple', '#9b59b6'),
    ('Yellow', '#f1c40f'),
]


def _default_camp_positions(width, height, n_colonies):
    """Corner camps inset 3 tiles. Supports 1..4 colonies; raises for more."""
    if n_colonies > 4:
        raise ValueError(f'colonies={n_colonies} exceeds supported 4')
    corners = [(3, 3), (width - 4, 3), (3, height - 4), (width - 4, height - 4)]
    return corners[:n_colonies]


def _build_default_colonies(width, height, n_colonies):
    positions = _default_camp_positions(width, height, n_colonies)
    palette = DEFAULT_COLONY_PALETTE[:n_colonies]
    out = []
    for (name, color), (cx, cy) in zip(palette, positions):
        out.append(EngineColony(
            id=None, name=name, color=color,
            camp_x=cx, camp_y=cy,
            food_stock=engine_config.INITIAL_FOOD_STOCK,
        ))
    return out


def create_simulation(width, height, seed=None, agent_count=0,
                      colonies=0, agents_per_colony=None):
    """Create a fresh sim. Two calling paths:
      * Legacy:   agent_count=N (pre-cultivation, no colony system).
      * Colonies: colonies=K + agents_per_colony=M (default demo path).
    Default kwargs keep every existing caller on the legacy path; T22
    wires the route to opt in explicitly.
    """
    global _current_sim

    # Colony kwargs travel as a pair. Half-set previously fell silently to
    # the legacy branch after already flushing Colony rows — loud at the
    # seam instead (mirrors the engine-layer guard in new_simulation).
    if bool(colonies) != (agents_per_colony is not None):
        raise ValueError(
            'colonies and agents_per_colony must be passed together; '
            f'got colonies={colonies!r}, agents_per_colony={agents_per_colony!r}'
        )

    try:
        db.session.query(models.Event).delete()
        db.session.query(models.Agent).delete()
        db.session.query(models.WorldTile).delete()
        db.session.query(models.Colony).delete()
        db.session.query(models.SimulationState).delete()
        db.session.flush()

        if colonies and agents_per_colony is not None:
            engine_colonies = _build_default_colonies(width, height, colonies)
            colony_rows = [mappers.colony_to_row(c) for c in engine_colonies]
            db.session.add_all(colony_rows)
            db.session.flush()
            for c, row in zip(engine_colonies, colony_rows):
                c.id = row.id

            sim = new_simulation(
                width, height, seed=seed,
                colonies=engine_colonies,
                agents_per_colony=agents_per_colony,
            )
        else:
            sim = new_simulation(
                width, height, seed=seed,
                agent_count=agent_count,
            )

        # Demo bootstrap: skip the opening dawn window so press-play starts
        # in the 'day' phase. Without this, a fresh sim spends the first
        # TICKS_PER_PHASE ticks on eat/rest/step-to-camp routines — visually
        # sleepy for an interview demo. Engine tests that construct their
        # own Simulation directly are untouched (this offset lives at the
        # service seam, not in engine.simulation).
        sim.current_tick = cycle.TICKS_PER_PHASE

        tile_rows = [mappers.tile_to_row(t) for row in sim.world.tiles for t in row]
        db.session.add_all(tile_rows)

        agent_rows = [mappers.agent_to_row(a) for a in sim.agents]
        db.session.add_all(agent_rows)
        db.session.flush()
        for agent, row in zip(sim.agents, agent_rows):
            agent.id = row.id

        state = models.SimulationState(
            current_tick=sim.current_tick,
            running=False, speed=1.0,
            world_width=width, world_height=height,
            seed=seed,
            **_rng_state_columns(sim),
        )
        db.session.add(state)

        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    _current_sim = sim
    return sim


def step_simulation(ticks=1):
    """Advance the current sim N ticks and persist deltas in one transaction.

    Persisted per step:
      * new Event rows (one per engine event)
      * updated WorldTile rows — tiles dirtied by foraged/planted/harvested/
        crop_matured events (resource_amount, crop_state, crop_growth_ticks,
        crop_colony_id)
      * updated Colony rows — food_stock deltas from harvested/ate_from_cache
      * updated Agent rows — alive agents mutate each tick
      * SimulationState — current_tick + RNG sub-stream snapshots
    """
    if not isinstance(ticks, int) or ticks < 1:
        raise ValueError(f'ticks must be a positive int, got {ticks!r}')
    if ticks > MAX_TICKS_PER_STEP:
        raise ValueError(
            f'ticks={ticks} exceeds MAX_TICKS_PER_STEP={MAX_TICKS_PER_STEP}'
        )
    sim = get_current_simulation()
    try:
        events = sim.run(ticks)

        event_rows = [mappers.event_to_row(e) for e in events]
        db.session.add_all(event_rows)

        dirty_tile_coords = {
            (e['data']['tile_x'], e['data']['tile_y'])
            for e in events
            if e['type'] in ('foraged', 'planted', 'harvested', 'crop_matured')
        }
        if dirty_tile_coords:
            _update_dirty_tiles(sim, dirty_tile_coords)

        dirty_colony_ids = {
            e['data']['colony_id']
            for e in events
            if e['type'] in ('harvested', 'ate_from_cache')
        }
        if dirty_colony_ids:
            _update_dirty_colonies(sim, dirty_colony_ids)

        _update_agents(sim)

        state = _load_state_row()
        state.current_tick = sim.current_tick
        rng_cols = _rng_state_columns(sim)
        state.rng_spawn_state = rng_cols['rng_spawn_state']
        state.rng_tick_state = rng_cols['rng_tick_state']

        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return events


def load_current_simulation():
    """Rebuild a Simulation from DB rows. Raises SimulationNotFoundError
    if no SimulationState row exists (i.e. nothing has ever been created).
    """
    state = db.session.query(models.SimulationState).one_or_none()
    if state is None:
        raise SimulationNotFoundError('no simulation has been created')

    tile_rows = db.session.query(models.WorldTile).all()
    world = mappers.rows_to_world(tile_rows, state.world_width, state.world_height)

    colony_rows = db.session.query(models.Colony).order_by(models.Colony.id).all()
    engine_colonies = [mappers.row_to_colony(r) for r in colony_rows]

    sim = Simulation(
        world=world,
        current_tick=state.current_tick,
        seed=state.seed,
        colonies=engine_colonies,
    )
    # growing_count isn't persisted (derived state, T12 contract). Delegate
    # to the engine's own recompute so service + step() share one definition
    # — if the growing rule ever changes, both sites follow.
    sim.recompute_growing_counts()

    agent_rows = db.session.query(models.Agent).all()
    for row in agent_rows:
        sim.agents.append(mappers.row_to_agent(row))

    if state.rng_spawn_state is not None and state.rng_tick_state is not None:
        sim.restore_rng_state({
            'spawn': state.rng_spawn_state,
            'tick': state.rng_tick_state,
        })

    return sim


def query_events(agent_id=None, since_tick=None, limit=100):
    """Query persisted events with optional filters.

    Always returns events in ascending (tick, id) order — the canonical
    replay stream (§2128). What changes with `since_tick` is *which window*
    of that stream we select:

      * `since_tick` set  — cursor mode. Events strictly after since_tick,
                            oldest-first, capped at `limit`. Used for delta
                            polling: client passes `last_seen_tick`, gets
                            only what it hasn't seen.
      * `since_tick` None — bootstrap mode. Return the latest `limit` events
                            (the tail of the stream), still in ascending
                            order. Fixes §9.32: previously returned the
                            HEAD of the stream, so the live log in
                            /world/state froze on tick 0 after ~50 ticks.

    Tail selection is done by ordering desc + limit + reversing in Python,
    which is O(limit) extra work and indexable via idx_events_tick (§9.17).

    Args:
      agent_id:   include only events for this agent id (or None for all).
      since_tick: include only events with tick > since_tick (exclusive —
                  so the client can pass `last_seen_tick` and avoid dupes).
      limit:      hard-cap on rows returned. Caller is responsible for
                  range-validating this (route layer enforces [1, 1000]).
    """
    q = db.session.query(models.Event)
    if agent_id is not None:
        q = q.filter(models.Event.agent_id == agent_id)
    if since_tick is not None:
        q = q.filter(models.Event.tick > since_tick)
        q = q.order_by(models.Event.tick.asc(), models.Event.id.asc()).limit(limit)
        return q.all()
    q = q.order_by(models.Event.tick.desc(), models.Event.id.desc()).limit(limit)
    return list(reversed(q.all()))


def _rng_state_columns(sim):
    snapshot = sim.snapshot_rng_state()
    return {
        'rng_spawn_state': snapshot['spawn'],
        'rng_tick_state': snapshot['tick'],
    }


def _load_state_row():
    # one_or_none not one(): we never expect zero rows here (step is called
    # on a live sim) but none() would raise MultipleResultsFound if the
    # singleton invariant ever broke — the .one() would give us the louder
    # signal, but the caller has already guaranteed the sim exists via
    # get_current_simulation, so this is strictly a persistence lookup.
    return db.session.query(models.SimulationState).one()


def _update_dirty_tiles(sim, coords):
    by_coord = {(t.x, t.y): t for row in sim.world.tiles for t in row if (t.x, t.y) in coords}
    rows = (
        db.session.query(models.WorldTile)
        .filter(
            tuple_(models.WorldTile.x, models.WorldTile.y).in_(list(coords))
        )
        .all()
    )
    for row in rows:
        mappers.update_tile_row(row, by_coord[(row.x, row.y)])


def _update_dirty_colonies(sim, colony_ids):
    """Write food_stock deltas from harvested/ate_from_cache events back to DB.

    Unlike `_update_agents` (agents die mid-tick, id-miss is legitimate),
    a colony that emitted an event *must* exist in `sim.colonies` — no
    lifecycle culls colonies. Index direct, let KeyError propagate so a
    reload-without-colonies or engine/service drift fails loud at the
    transaction boundary instead of silently dropping food_stock.
    """
    rows = (
        db.session.query(models.Colony)
        .filter(models.Colony.id.in_(colony_ids))
        .all()
    )
    for row in rows:
        mappers.update_colony_row(row, sim.colonies[row.id])


def _update_agents(sim):
    id_to_engine = {a.id: a for a in sim.agents if a.id is not None}
    if not id_to_engine:
        return
    rows = (
        db.session.query(models.Agent)
        .filter(models.Agent.id.in_(id_to_engine.keys()))
        .all()
    )
    for row in rows:
        mappers.update_agent_row(row, id_to_engine[row.id])
