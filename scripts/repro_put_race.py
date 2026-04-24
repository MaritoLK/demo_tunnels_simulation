"""Reproduce the tick_loop FK violation triggered by PUT /simulation while
the sim is running. If this fires, the tick_loop auto-pauses — which in
the running frontend presents as agents freezing / teleporting when the
user triggers regen mid-run.
"""
from __future__ import annotations

import json
import time
import urllib.request

API = 'http://127.0.0.1:5000/api/v1'


def http(method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f'{API}{path}', data=data, method=method,
        headers={'Content-Type': 'application/json'} if data else {},
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def put_sim() -> dict:
    return http('PUT', '/simulation', {
        'width': 40, 'height': 30, 'seed': 42,
        'colonies': 4, 'agents_per_colony': 3,
    })


def main() -> None:
    print('[1] creating sim')
    put_sim()
    http('PATCH', '/simulation/control', {'running': True, 'speed': 1.0})
    time.sleep(3)
    state = http('GET', '/simulation')
    print(f'[2] running 3s: tick={state["tick"]} running={state["running"]}')

    print('[3] PUT /simulation while running (race)')
    put_sim()
    http('PATCH', '/simulation/control', {'running': True, 'speed': 1.0})

    for i in range(10):
        time.sleep(1)
        state = http('GET', '/simulation')
        print(f'  [t+{i+1}s] tick={state["tick"]} running={state["running"]}')


if __name__ == '__main__':
    main()
