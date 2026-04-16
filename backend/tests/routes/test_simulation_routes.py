"""HTTP surface: happy-path + error-path coverage via Flask test client."""
import json

import pytest


API = '/api/v1'


def _put(client, body):
    return client.put(
        f'{API}/simulation',
        data=json.dumps(body),
        content_type='application/json',
    )


def _post_step(client, body):
    return client.post(
        f'{API}/simulation/step',
        data=json.dumps(body),
        content_type='application/json',
    )


# --- happy paths ---------------------------------------------------------

def test_health_is_outside_versioned_api(client):
    resp = client.get('/api/health')
    assert resp.status_code == 200
    assert resp.get_json() == {'status': 'ok'}


def test_put_simulation_returns_summary(client):
    resp = _put(client, {'width': 6, 'height': 6, 'seed': 11, 'agent_count': 2})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['tick'] == 0
    assert body['width'] == 6 and body['height'] == 6
    assert body['seed'] == 11
    assert body['agent_count'] == 2


def test_get_simulation_after_put(client):
    _put(client, {'width': 5, 'height': 5, 'agent_count': 1})
    resp = client.get(f'{API}/simulation')
    assert resp.status_code == 200
    assert resp.get_json()['tick'] == 0


def test_get_simulation_cold_returns_404(client):
    resp = client.get(f'{API}/simulation')
    assert resp.status_code == 404
    assert 'error' in resp.get_json()


def test_post_step_advances_tick_and_returns_events(client):
    _put(client, {'width': 5, 'height': 5, 'seed': 3, 'agent_count': 2})
    resp = _post_step(client, {'ticks': 5})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['tick'] == 5
    assert 'events' in body


def test_get_world_shape(client):
    _put(client, {'width': 4, 'height': 3, 'seed': 1, 'agent_count': 0})
    resp = client.get(f'{API}/world')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['width'] == 4 and body['height'] == 3
    assert len(body['tiles']) == 3 and len(body['tiles'][0]) == 4


def test_get_agents_returns_list(client):
    _put(client, {'width': 5, 'height': 5, 'seed': 1, 'agent_count': 3})
    resp = client.get(f'{API}/agents')
    assert resp.status_code == 200
    assert len(resp.get_json()['agents']) == 3


def test_get_events_wire_rename_type(client):
    _put(client, {'width': 5, 'height': 5, 'seed': 1, 'agent_count': 2})
    _post_step(client, {'ticks': 5})
    resp = client.get(f'{API}/events?limit=10')
    assert resp.status_code == 200
    events = resp.get_json()['events']
    assert events, 'expected persisted events after stepping'
    # §9.21: wire format uses `type`, not `event_type` (the DB col name).
    assert 'type' in events[0] and 'event_type' not in events[0]


def test_get_events_since_tick_exclusive(client):
    _put(client, {'width': 5, 'height': 5, 'seed': 1, 'agent_count': 2})
    _post_step(client, {'ticks': 10})
    resp = client.get(f'{API}/events?since_tick=5&limit=1000')
    for e in resp.get_json()['events']:
        assert e['tick'] > 5


def test_get_events_since_tick_minus_one_includes_tick_zero(client):
    # B1 fix: `since_tick` is exclusive (`tick > N`), and tick numbering
    # starts at 0 — events from the very first engine step are tagged
    # tick=0. A client that passes since_tick=0 to "get everything new"
    # would drop those tick-0 events. Convention: pass since_tick=-1 to
    # mean "everything from tick 0 onward." The route must accept -1.
    _put(client, {'width': 5, 'height': 5, 'seed': 1, 'agent_count': 2})
    _post_step(client, {'ticks': 1})
    resp = client.get(f'{API}/events?since_tick=-1&limit=1000')
    assert resp.status_code == 200
    events = resp.get_json()['events']
    assert any(e['tick'] == 0 for e in events), 'tick-0 events must be reachable via since_tick=-1'


def test_get_world_state_since_tick_minus_one_includes_tick_zero(client):
    # Same invariant for the composite polling endpoint.
    _put(client, {'width': 5, 'height': 5, 'seed': 1, 'agent_count': 2})
    _post_step(client, {'ticks': 1})
    resp = client.get(f'{API}/world/state?since_tick=-1')
    events = resp.get_json()['events']
    assert any(e['tick'] == 0 for e in events)


# --- /world/state composite endpoint -------------------------------------
#
# One endpoint so the polling loop is a single round-trip. Response shape:
#   { "sim": {...summary...}, "world": {...}, "agents": [...], "events": [...] }
# `events` is filtered by `since_tick` (exclusive) when provided, else empty.
# Rationale: polling clients track last_seen_tick and only want the delta.
# First-load history is a separate one-time fetch, keeping the per-poll
# payload stable in size.

def test_get_world_state_cold_returns_404(client):
    resp = client.get(f'{API}/world/state')
    assert resp.status_code == 404


def test_get_world_state_composes_all_sections(client):
    _put(client, {'width': 4, 'height': 3, 'seed': 1, 'agent_count': 2})
    resp = client.get(f'{API}/world/state')
    assert resp.status_code == 200
    body = resp.get_json()
    assert set(body.keys()) >= {'sim', 'world', 'agents', 'events'}
    assert body['sim']['width'] == 4
    assert body['sim']['height'] == 3
    assert body['world']['width'] == 4
    assert len(body['world']['tiles']) == 3
    assert len(body['agents']) == 2


def test_get_world_state_returns_recent_events_without_since_tick(client):
    _put(client, {'width': 5, 'height': 5, 'seed': 1, 'agent_count': 2})
    _post_step(client, {'ticks': 5})
    resp = client.get(f'{API}/world/state')
    # No since_tick → recent events (default limit). Lets a cold-load
    # polling client bootstrap without a separate /events call.
    assert len(resp.get_json()['events']) > 0


def test_get_world_state_filters_events_by_since_tick(client):
    _put(client, {'width': 5, 'height': 5, 'seed': 1, 'agent_count': 2})
    _post_step(client, {'ticks': 10})
    resp = client.get(f'{API}/world/state?since_tick=5')
    body = resp.get_json()
    for e in body['events']:
        assert e['tick'] > 5


def test_patch_simulation_control_sets_running(client):
    _put(client, {'width': 3, 'height': 3, 'seed': 1, 'agent_count': 1})
    resp = client.patch(
        f'{API}/simulation/control',
        data=json.dumps({'running': True}),
        content_type='application/json',
    )
    assert resp.status_code == 200
    assert resp.get_json()['running'] is True
    # Persists: subsequent GET sees the new value.
    assert client.get(f'{API}/world/state').get_json()['sim']['running'] is True


def test_patch_simulation_control_sets_speed(client):
    _put(client, {'width': 3, 'height': 3, 'seed': 1, 'agent_count': 1})
    resp = client.patch(
        f'{API}/simulation/control',
        data=json.dumps({'speed': 2.5}),
        content_type='application/json',
    )
    assert resp.status_code == 200
    assert resp.get_json()['speed'] == 2.5


def test_patch_simulation_control_partial_does_not_clobber_other_field(client):
    _put(client, {'width': 3, 'height': 3, 'seed': 1, 'agent_count': 1})
    # Set speed first.
    client.patch(
        f'{API}/simulation/control',
        data=json.dumps({'speed': 3.0}),
        content_type='application/json',
    )
    # Now set running only — speed must stay at 3.0.
    client.patch(
        f'{API}/simulation/control',
        data=json.dumps({'running': True}),
        content_type='application/json',
    )
    sim = client.get(f'{API}/world/state').get_json()['sim']
    assert sim['running'] is True
    assert sim['speed'] == 3.0


def test_patch_simulation_control_rejects_invalid_speed(client):
    _put(client, {'width': 3, 'height': 3, 'seed': 1, 'agent_count': 1})
    resp = client.patch(
        f'{API}/simulation/control',
        data=json.dumps({'speed': -1.0}),
        content_type='application/json',
    )
    assert resp.status_code == 400


def test_get_world_state_exposes_running_and_speed(client):
    # running + speed live on simulation_state. §9.27 background thread
    # reads them to drive the tick loop — composite endpoint must surface
    # them so the frontend can gate polling on running and render speed.
    _put(client, {'width': 3, 'height': 3, 'seed': 1, 'agent_count': 1})
    resp = client.get(f'{API}/world/state')
    sim = resp.get_json()['sim']
    assert 'running' in sim
    assert 'speed' in sim


# --- error paths ---------------------------------------------------------

def test_put_rejects_non_int_width(client):
    resp = _put(client, {'width': 'big', 'height': 5})
    assert resp.status_code == 400


def test_put_rejects_oversized_world(client):
    resp = _put(client, {'width': 1000, 'height': 1000, 'agent_count': 0})
    assert resp.status_code == 400


def test_put_rejects_too_many_agents(client):
    resp = _put(client, {'width': 4, 'height': 4, 'agent_count': 100})
    assert resp.status_code == 400


def test_put_rejects_missing_body(client):
    resp = client.put(f'{API}/simulation', data='', content_type='application/json')
    assert resp.status_code == 400


def test_put_rejects_malformed_json(client):
    resp = client.put(
        f'{API}/simulation',
        data=b'not json at all',
        content_type='application/json',
    )
    assert resp.status_code == 400


def test_put_rejects_non_int_seed(client):
    resp = _put(client, {'width': 4, 'height': 4, 'seed': 'abc', 'agent_count': 0})
    assert resp.status_code == 400


def test_step_rejects_too_many_ticks(client):
    _put(client, {'width': 3, 'height': 3, 'seed': 1, 'agent_count': 1})
    resp = _post_step(client, {'ticks': 10_000})
    assert resp.status_code == 400


def test_step_rejects_zero_ticks(client):
    _put(client, {'width': 3, 'height': 3, 'seed': 1, 'agent_count': 1})
    resp = _post_step(client, {'ticks': 0})
    assert resp.status_code == 400


def test_events_rejects_bad_agent_id(client):
    resp = client.get(f'{API}/events?agent_id=abc')
    assert resp.status_code == 400


def test_events_rejects_oversized_limit(client):
    resp = client.get(f'{API}/events?limit=99999')
    assert resp.status_code == 400


def test_unknown_route_is_404(client):
    resp = client.get(f'{API}/nope')
    assert resp.status_code == 404


def test_world_state_includes_sim_day_and_phase(client, db_session):
    client.put(f'{API}/simulation', data=json.dumps({
        'width': 20, 'height': 20, 'seed': 1,
        'agent_count': 3,
    }), content_type='application/json')
    resp = client.get(f'{API}/world/state')
    assert resp.status_code == 200
    body = resp.get_json()
    assert 'day' in body['sim']
    assert 'phase' in body['sim']
    assert body['sim']['phase'] == 'dawn'
    assert body['sim']['day'] == 0


def test_agent_includes_colony_id(client, db_session):
    client.put(f'{API}/simulation', data=json.dumps({
        'width': 20, 'height': 20, 'seed': 1,
        'agent_count': 3,
    }), content_type='application/json')
    body = client.get(f'{API}/world/state').get_json()
    for a in body['agents']:
        assert 'colony_id' in a    # legacy agents have colony_id=None


def test_tile_includes_crop_fields(client, db_session):
    client.put(f'{API}/simulation', data=json.dumps({
        'width': 20, 'height': 20, 'seed': 1,
        'agent_count': 3,
    }), content_type='application/json')
    body = client.get(f'{API}/world/state').get_json()
    sample = body['world']['tiles'][0][0]
    assert 'crop_state' in sample
    assert 'crop_growth_ticks' in sample
    assert 'crop_colony_id' in sample
