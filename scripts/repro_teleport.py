"""Reproduce the teleport/stiff-movement bug by capturing real poll stream
and replicating the frontend Canvas2DRenderer interpolation math on it.

Runs with the local docker stack up. Does NOT depend on the frontend running.

Outputs:
  * A summary table of tick-advance events and agent deltas.
  * A list of snap-guard trip events (where dx*dx + dy*dy > 2).
  * The alpha timeline a renderer would have computed, with gaps where
    alpha would be clamped at 1.0 (i.e. agent frozen mid-tick waiting
    for next snapshot).
"""
from __future__ import annotations

import json
import time
import urllib.request
from collections import defaultdict

API = 'http://127.0.0.1:5000/api/v1'
POLL_MS = 500
CAPTURE_SEC = int(__import__('os').environ.get('CAPTURE_SEC', '30'))
SEED = 42
WIDTH = 40
HEIGHT = 30
COLONIES = 4
AGENTS_PER = 3
SPEED = 1.0

# Renderer constants mirrored from frontend/src/render/Canvas2DRenderer.ts
FRONTEND_POLL_INTERVAL_MS = 500  # seed for pollIntervalMs EMA
SNAP_THRESHOLD = 2  # if dx*dx + dy*dy > SNAP_THRESHOLD → teleport (no lerp)
EMA_NEW_WEIGHT = 0.3
EMA_OLD_WEIGHT = 0.7


def http(method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f'{API}{path}',
        data=data,
        method=method,
        headers={'Content-Type': 'application/json'} if data else {},
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def setup_sim() -> None:
    print(f'[setup] creating sim {WIDTH}x{HEIGHT} seed={SEED} '
          f'colonies={COLONIES} agents_per={AGENTS_PER}')
    http('PUT', '/simulation', {
        'width': WIDTH, 'height': HEIGHT, 'seed': SEED,
        'colonies': COLONIES, 'agents_per_colony': AGENTS_PER,
    })
    print(f'[setup] starting at speed={SPEED}')
    http('PATCH', '/simulation/control', {'running': True, 'speed': SPEED})


def capture() -> list[dict]:
    """Poll at POLL_MS for CAPTURE_SEC. Return raw sample list."""
    samples: list[dict] = []
    start = time.monotonic()
    deadline = start + CAPTURE_SEC
    next_poll = start
    while time.monotonic() < deadline:
        t = time.monotonic()
        if t < next_poll:
            time.sleep(next_poll - t)
        poll_start = time.monotonic()
        data = http('GET', '/world/state')
        poll_end = time.monotonic()
        samples.append({
            't_ms': (poll_start - start) * 1000,
            'rtt_ms': (poll_end - poll_start) * 1000,
            'tick': data['sim']['tick'],
            'running': data['sim']['running'],
            'agents': {a['id']: (a['x'], a['y'], a['alive']) for a in data['agents']},
        })
        next_poll += POLL_MS / 1000
    return samples


def analyze(samples: list[dict]) -> None:
    print(f'\n[samples] captured {len(samples)} polls over {CAPTURE_SEC}s')

    # 1. Poll timing jitter
    intervals = [samples[i]['t_ms'] - samples[i-1]['t_ms']
                 for i in range(1, len(samples))]
    print(f'[poll-timing] min={min(intervals):.0f}ms max={max(intervals):.0f}ms '
          f'avg={sum(intervals)/len(intervals):.0f}ms (target={POLL_MS}ms)')

    # 2. Tick advances per poll
    tick_deltas = [samples[i]['tick'] - samples[i-1]['tick']
                   for i in range(1, len(samples))]
    td_hist = defaultdict(int)
    for d in tick_deltas:
        td_hist[d] += 1
    print(f'[tick-deltas] per-poll tick advance histogram: '
          f'{dict(sorted(td_hist.items()))}')
    if any(d > 1 for d in tick_deltas):
        print('  ⚠ tick jumped > 1 between polls — snapshot missed intermediate state')

    # 3. Id appear/disappear
    appear_events = []
    disappear_events = []
    for i in range(1, len(samples)):
        prev_ids = set(samples[i-1]['agents'].keys())
        curr_ids = set(samples[i]['agents'].keys())
        for aid in curr_ids - prev_ids:
            appear_events.append((i, aid))
        for aid in prev_ids - curr_ids:
            disappear_events.append((i, aid))
    print(f'[lifecycle] appears={len(appear_events)} disappears={len(disappear_events)}')
    if appear_events:
        print(f'  appear samples: {appear_events[:5]}')
    if disappear_events:
        print(f'  disappear samples: {disappear_events[:5]}')

    # 4. Per-agent per-poll position deltas → snap detection
    snaps = []
    big_moves = []
    for i in range(1, len(samples)):
        prev_ags = samples[i-1]['agents']
        curr_ags = samples[i]['agents']
        for aid, (cx, cy, alive) in curr_ags.items():
            if aid not in prev_ags:
                continue
            px, py, _ = prev_ags[aid]
            dx, dy = cx - px, cy - py
            d2 = dx * dx + dy * dy
            if d2 > 0:
                big_moves.append((i, aid, d2, (px, py), (cx, cy)))
                if d2 > SNAP_THRESHOLD:
                    snaps.append((i, aid, d2, (px, py), (cx, cy),
                                  samples[i-1]['tick'], samples[i]['tick']))
    print(f'[position] total moves observed between polls: {len(big_moves)}')
    print(f'[snap-trips] events where dx²+dy² > {SNAP_THRESHOLD}: {len(snaps)}')
    if snaps:
        print('  first 10 snap events (poll_idx, agent_id, d², from, to, '
              'prev_tick, curr_tick):')
        for ev in snaps[:10]:
            print(f'    {ev}')

    # 5. Replicate renderer interpolation math per sample
    # Track: lastSeenTick, lastTickBoundaryAt, pollIntervalMs, prevPositions, lastSeenPositions
    print('\n[replicate-renderer] running renderer math on captured stream')
    last_seen_tick = -1
    last_tick_boundary_at = 0.0  # ms
    poll_interval_ms = FRONTEND_POLL_INTERVAL_MS
    prev_positions: dict[int, tuple[int, int]] = {}
    last_seen_positions: dict[int, tuple[int, int]] = {}

    frozen_windows = 0  # how many polls had alpha already at 1.0 before receive
    renderer_snaps = 0  # snap-guard events from the renderer's perspective

    for s in samples:
        now = s['t_ms']
        current_tick = s['tick']
        tick_advanced = current_tick > last_seen_tick
        if tick_advanced and last_seen_tick >= 0:
            prev_positions = dict(last_seen_positions)
            delta = now - last_tick_boundary_at
            if 0 < delta < 3000:
                poll_interval_ms = (
                    poll_interval_ms * EMA_OLD_WEIGHT + delta * EMA_NEW_WEIGHT
                )
            last_tick_boundary_at = now
        elif last_seen_tick < 0:
            last_tick_boundary_at = now
        last_seen_tick = current_tick

        alpha = max(0.0, min(1.0, (now - last_tick_boundary_at) / poll_interval_ms))
        if alpha >= 1.0 and last_seen_tick >= 1:
            frozen_windows += 1

        # Snap guard trip per renderer's logic
        for aid, (cx, cy, _) in s['agents'].items():
            if aid in prev_positions:
                px, py = prev_positions[aid]
                dx, dy = cx - px, cy - py
                if dx * dx + dy * dy > SNAP_THRESHOLD:
                    renderer_snaps += 1

        for aid, (cx, cy, _) in s['agents'].items():
            last_seen_positions[aid] = (cx, cy)

    print(f'  final pollIntervalMs EMA: {poll_interval_ms:.1f}ms')
    print(f'  frozen-at-target windows (alpha pinned to 1.0): {frozen_windows}')
    print(f'  renderer snap-guard trips total: {renderer_snaps}')


def main() -> None:
    setup_sim()
    # Let the sim settle one tick so we're not capturing from a cold-start
    time.sleep(1.0)
    samples = capture()
    analyze(samples)
    # Pause sim so we don't leave it running
    http('PATCH', '/simulation/control', {'running': False})


if __name__ == '__main__':
    main()
