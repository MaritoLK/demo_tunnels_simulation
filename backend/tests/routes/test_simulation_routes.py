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
