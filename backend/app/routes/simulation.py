"""HTTP surface for the simulation.

Design choices (see STUDY_NOTES §9.21):
  * Single blueprint — every route is sim-scoped, so one error domain, one
    cache, one URL prefix. Splitting into per-resource blueprints buys
    nothing here.
  * url_prefix lives at register_blueprint() time, not on the blueprint
    object — versioning (`/api/v2`) becomes a one-line mount change.
  * Routes never import models or engine directly. Service layer is the
    only gateway; errors flow up as SimulationError subclasses and are
    translated to HTTP at the app-level errorhandler.
  * Input validation is route-layer (JSON shape → int coercion → range
    check). The engine + service re-validate the same invariants — the
    route is the *shape* gate, the engine is the *trust* boundary.

No auth. Single-user demo. Do not expose beyond localhost.
"""
from flask import Blueprint, abort, request

from app.services import simulation_service

from . import serializers


bp = Blueprint('simulation', __name__)


# Route-layer validation bounds. Mirror engine/service caps so the bad
# request gets rejected with a useful 400 before it wastes a DB round-trip.
MAX_WORLD_CELLS = 10_000
MAX_AGENTS = 1000
MAX_TICKS_PER_STEP = 1000
MAX_EVENTS_LIMIT = 1000
DEFAULT_EVENTS_LIMIT = 100
_INT64_MIN = -(2 ** 63)
_INT64_MAX = 2 ** 63 - 1


def _bad(message, **details):
    """Return a 400 with the project's canonical error shape."""
    payload = {'error': message}
    if details:
        payload['details'] = details
    abort(400, description=payload)


def _require_int(value, name, *, min=None, max=None, allow_none=False):
    if value is None:
        if allow_none:
            return None
        _bad(f'{name} is required')
    if isinstance(value, bool) or not isinstance(value, int):
        _bad(f'{name} must be an int', field=name, got=repr(value))
    if min is not None and value < min:
        _bad(f'{name} must be >= {min}', field=name, got=value)
    if max is not None and value > max:
        _bad(f'{name} must be <= {max}', field=name, got=value)
    return value


def _query_int(name, *, default=None, min=None, max=None, allow_none=False):
    """Parse a query-string int, 400ing on garbage rather than silently None."""
    raw = request.args.get(name)
    if raw is None or raw == '':
        if allow_none or default is not None:
            return default
        _bad(f'{name} query param is required')
    try:
        value = int(raw)
    except (TypeError, ValueError):
        _bad(f'{name} must be an int', field=name, got=raw)
    if min is not None and value < min:
        _bad(f'{name} must be >= {min}', field=name, got=value)
    if max is not None and value > max:
        _bad(f'{name} must be <= {max}', field=name, got=value)
    return value


@bp.put('/simulation')
def replace_simulation():
    """Replace the current singleton sim. Idempotent for a given body.

    PUT (not POST + 201) because there is no addressable new resource —
    this wipes and rebuilds the singleton. See §9.21.

    Two mutually-exclusive calling shapes:
      * Random spawn: `agent_count=N` (default colony, random tiles).
      * Colonies: `colonies=K, agents_per_colony=M` (4-colony demo layout).
    """
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        _bad('request body must be a JSON object')

    width = _require_int(body.get('width'), 'width', min=1)
    height = _require_int(body.get('height'), 'height', min=1)
    if width * height > MAX_WORLD_CELLS:
        _bad(
            f'width*height={width * height} exceeds MAX_WORLD_CELLS={MAX_WORLD_CELLS}',
            field='width*height',
        )

    seed = _require_int(
        body.get('seed'), 'seed',
        min=_INT64_MIN, max=_INT64_MAX, allow_none=True,
    )

    colonies = _require_int(
        body.get('colonies'), 'colonies',
        min=0, max=4, allow_none=True,
    )
    agents_per_colony = _require_int(
        body.get('agents_per_colony'), 'agents_per_colony',
        min=0, max=10, allow_none=True,
    )

    # Gate 1 of 3 for the paired-kwargs invariant (service + engine are the
    # downstream gates). Must stay above `create_simulation` — that call's
    # first act is `DELETE FROM ...` on every sim table, so a silent pass-
    # through here would wipe state before the service raised. Form matches
    # the engine-layer guard at `new_simulation` for pattern consistency.
    if (colonies is None) != (agents_per_colony is None):
        _bad(
            'colonies and agents_per_colony must be passed together',
            field='colonies/agents_per_colony',
            colonies=colonies, agents_per_colony=agents_per_colony,
        )

    agent_count = None
    if not colonies:
        agent_count = _require_int(
            body.get('agent_count', 0), 'agent_count',
            min=0, max=min(width * height, MAX_AGENTS),
        )

    sim = simulation_service.create_simulation(
        width=width, height=height, seed=seed,
        colonies=colonies or 0,
        agents_per_colony=agents_per_colony,
        agent_count=agent_count,
    )
    control = simulation_service.get_simulation_control()
    time = simulation_service.time_snapshot()
    return serializers.simulation_summary(sim, control, time), 200


@bp.get('/simulation')
def get_simulation():
    sim = simulation_service.get_current_simulation()
    control = simulation_service.get_simulation_control()
    time = simulation_service.time_snapshot()
    return serializers.simulation_summary(sim, control, time), 200


@bp.patch('/simulation/control')
def patch_simulation_control():
    """Partial update of {running, speed}. PATCH semantics: omitted fields
    are untouched. The background tick thread (§9.27) polls these flags
    to drive itself — running gates the loop, speed sets the sleep.
    """
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        _bad('request body must be a JSON object')
    running = body.get('running')
    speed = body.get('speed')
    if running is None and speed is None:
        _bad('at least one of {running, speed} must be provided')
    if running is not None and not isinstance(running, bool):
        _bad('running must be a boolean', field='running', got=repr(running))
    if speed is not None:
        if isinstance(speed, bool) or not isinstance(speed, (int, float)):
            _bad('speed must be a number', field='speed', got=repr(speed))
        if speed < simulation_service.MIN_SPEED or speed > simulation_service.MAX_SPEED:
            _bad(
                f'speed out of range [{simulation_service.MIN_SPEED}, '
                f'{simulation_service.MAX_SPEED}]',
                field='speed', got=speed,
            )
    updated = simulation_service.update_simulation_control(
        running=running, speed=speed,
    )
    return updated, 200


@bp.post('/simulation/step')
def step_simulation():
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        _bad('request body must be a JSON object')
    ticks = _require_int(
        body.get('ticks', 1), 'ticks', min=1, max=MAX_TICKS_PER_STEP,
    )

    events = simulation_service.step_simulation(ticks=ticks)
    sim = simulation_service.get_current_simulation()
    return {
        'tick': sim.current_tick,
        'events': [serializers.engine_event_to_dict(e) for e in events],
    }, 200


@bp.get('/world')
def get_world():
    sim = simulation_service.get_current_simulation()
    return serializers.world_to_dict(sim.world), 200


@bp.get('/world/state')
def get_world_state():
    """Composite polling endpoint — one request returns the full frame.

    Shape:
      { sim: {...summary...}, world: {...}, agents: [...], events: [...], colonies: [...] }

    `events` default: the latest `limit` events (service tails the stream
    via desc+limit+reverse; see §9.32). When `since_tick` is provided,
    only events with tick > since_tick are returned (delta-style,
    exclusive). The default makes the endpoint self-sufficient for a
    cold-load polling client — no separate history bootstrap needed.
    The nginx micro-cache (§9.27d) keeps the repeated "last 100" payload
    from hammering the DB: one cache entry per sim per 1s window
    (nginx proxy_cache_valid requires integer seconds — see nginx.conf).
    """
    # Min is -1, not 0: engine ticks start at 0 so tick-0 events exist,
    # and `since_tick` filter is exclusive (`tick > N`). A client that
    # wants "all events from the start" passes -1. See §9.28 B1 fix.
    since_tick = _query_int('since_tick', allow_none=True, min=-1)
    limit = _query_int(
        'limit', default=DEFAULT_EVENTS_LIMIT,
        min=1, max=MAX_EVENTS_LIMIT,
    )
    sim = simulation_service.get_current_simulation()
    control = simulation_service.get_simulation_control()
    time = simulation_service.time_snapshot()
    event_rows = simulation_service.query_events(
        since_tick=since_tick, limit=limit,
    )
    return {
        'sim': serializers.simulation_summary(sim, control, time),
        'world': serializers.world_to_dict(sim.world),
        'agents': [serializers.agent_to_dict(a) for a in sim.agents],
        'events': [serializers.event_row_to_dict(r) for r in event_rows],
        'colonies': [
            serializers.colony_to_dict(c)
            for c in sorted(sim.colonies.values(), key=lambda c: c.id)
        ],
    }, 200


@bp.get('/agents')
def get_agents():
    sim = simulation_service.get_current_simulation()
    return {
        'agents': [serializers.agent_to_dict(a) for a in sim.agents],
    }, 200


@bp.get('/events')
def get_events():
    agent_id = _query_int('agent_id', allow_none=True, min=1)
    # See /world/state for the -1 convention.
    since_tick = _query_int('since_tick', allow_none=True, min=-1)
    limit = _query_int(
        'limit', default=DEFAULT_EVENTS_LIMIT,
        min=1, max=MAX_EVENTS_LIMIT,
    )
    rows = simulation_service.query_events(
        agent_id=agent_id, since_tick=since_tick, limit=limit,
    )
    return {
        'events': [serializers.event_row_to_dict(r) for r in rows],
    }, 200
