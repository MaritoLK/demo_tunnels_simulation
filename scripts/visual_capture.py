"""Headless-browser visual capture of the running frontend.

Creates a fresh sim via the API, then opens http://localhost in headless
Chromium, generates the world via the UI if needed (but we set it up via
API to bypass UI), takes screenshots at a fixed interval, and reports the
frames. Claude can then visually inspect the PNGs for teleport/stiff/
appear-disappear symptoms.

Run via: /tmp/pw-venv/bin/python scripts/visual_capture.py
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import sys
import time
import urllib.request

from playwright.async_api import async_playwright

API = 'http://127.0.0.1:5000/api/v1'
FRONTEND = 'http://127.0.0.1:5173'  # vite dev server direct
OUT_DIR = pathlib.Path('/tmp/vis_capture')
FRAME_INTERVAL_MS = 100  # 10 fps to catch mid-interpolation smoothly
FRAME_COUNT = 40  # 4 seconds of capture (covers ~4 ticks at speed 1)
SEED = 42
WIDTH = 40
HEIGHT = 30
COLONIES = 4
AGENTS_PER = 3


def http(method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f'{API}{path}', data=data, method=method,
        headers={'Content-Type': 'application/json'} if data else {},
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


async def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for p in OUT_DIR.glob('*.png'):
        p.unlink()
    for p in OUT_DIR.glob('*.json'):
        p.unlink()

    # Seed the sim via API (bypass the UI "generate" step).
    print('[setup] creating sim via API')
    http('PUT', '/simulation', {
        'width': WIDTH, 'height': HEIGHT, 'seed': SEED,
        'colonies': COLONIES, 'agents_per_colony': AGENTS_PER,
    })
    # Record tick before setting running so we can verify it advances.
    pre_state = http('GET', '/simulation')
    pre_tick = pre_state['tick']
    print(f'[setup] pre-start tick={pre_tick}')

    http('PATCH', '/simulation/control', {'running': True, 'speed': 1.0})

    # Sanity wait: give the sim 2 s to advance at least a few ticks.
    await asyncio.sleep(2.0)
    post_start_state = http('GET', '/simulation')
    post_start_tick = post_start_state['tick']
    print(f'[setup] post-start tick={post_start_tick} (delta={post_start_tick - pre_tick})')
    if post_start_tick <= pre_tick:
        print(
            '[WARNING] sim tick did not advance after 2 s — capture will proceed but '
            'analyze_frames.py will report a gate failure. Check the tick_loop / sim lock.',
            file=sys.stderr,
        )

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=['--disable-dev-shm-usage', '--no-sandbox'],
        )
        ctx = await browser.new_context(viewport={'width': 1400, 'height': 900})
        page = await ctx.new_page()

        # Console errors surface here.
        page.on('console', lambda msg: print(f'[browser-console] {msg.type}: {msg.text}'))
        page.on('pageerror', lambda err: print(f'[browser-error] {err}'))

        print(f'[browser] loading {FRONTEND}')
        await page.goto(FRONTEND, wait_until='networkidle', timeout=30000)

        # Wait for canvas to appear (world rendered).
        canvas = page.locator('canvas').first
        await canvas.wait_for(timeout=15000)
        await asyncio.sleep(2.5)  # let the render loop settle + sprites load

        # Sanity: verify the API thinks sim is running before capture.
        state = http('GET', '/simulation')
        print(f'[pre-capture] sim running={state["running"]} tick={state["tick"]}')

        print(f'[capture] taking {FRAME_COUNT} frames at {FRAME_INTERVAL_MS}ms (canvas + JSON)')
        t0 = time.monotonic()
        for i in range(FRAME_COUNT):
            elapsed_ms = (time.monotonic() - t0) * 1000
            stem = f'frame_{i:03d}_t{int(elapsed_ms):05d}ms'

            # PNG capture (canvas-only).
            out_png = OUT_DIR / f'{stem}.png'
            await canvas.screenshot(path=str(out_png))

            # JSON state dump via browser fetch (goes through nginx, same origin).
            state_json = await page.evaluate("""async () => {
  const r = await fetch('/api/v1/world/state');
  return await r.json();
}""")
            (OUT_DIR / f'{stem}.json').write_text(
                json.dumps({
                    'tick': state_json['sim']['tick'],
                    'server_time_ms': state_json['sim'].get('server_time_ms'),
                    'agents': [
                        {'id': a['id'], 'x': a['x'], 'y': a['y'], 'alive': a['alive']}
                        for a in state_json['agents']
                    ],
                })
            )

            await asyncio.sleep(FRAME_INTERVAL_MS / 1000)
        print(f'[capture] done {FRAME_COUNT} frames')

        state = http('GET', '/simulation')
        print(f'[post-capture] sim running={state["running"]} tick={state["tick"]}')
        print(f'[post-capture] pre-capture tick={pre_tick}, delta={state["tick"] - pre_tick}')

        await browser.close()

    http('PATCH', '/simulation/control', {'running': False})
    print(f'\n[done] frames in {OUT_DIR}/')


if __name__ == '__main__':
    asyncio.run(main())
