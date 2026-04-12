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

    agent_count = _require_int(
        body.get('agent_count', 0),
        'agent_count',
        min=0,
        max=min(width * height, MAX_AGENTS),
    )

    seed = _require_int(
        body.get('seed'), 'seed',
        min=_INT64_MIN, max=_INT64_MAX, allow_none=True,
    )

    sim = simulation_service.create_simulation(
        width=width, height=height, seed=seed, agent_count=agent_count,
    )
    return serializers.simulation_summary(sim), 200


@bp.get('/simulation')
def get_simulation():
    sim = simulation_service.get_current_simulation()
    return serializers.simulation_summary(sim), 200


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


@bp.get('/agents')
def get_agents():
    sim = simulation_service.get_current_simulation()
    return {
        'agents': [serializers.agent_to_dict(a) for a in sim.agents],
    }, 200


@bp.get('/events')
def get_events():
    agent_id = _query_int('agent_id', allow_none=True, min=1)
    since_tick = _query_int('since_tick', allow_none=True, min=0)
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
