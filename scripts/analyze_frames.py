"""Post-process the JSON dumps from visual_capture.py:
  * detect any per-agent dx²+dy² > 8 between consecutive frames
    (i.e. a visual teleport even after Tier 2's widening)
  * detect any flicker (id present → absent → present within 2 s)
  * print the server-time spacing to confirm the stream cadence
"""
import json
import pathlib
import sys

OUT_DIR = pathlib.Path('/tmp/vis_capture')


def main():
    frames = sorted(OUT_DIR.glob('frame_*.json'))
    if not frames:
        print('no frames found — did visual_capture.py run?')
        sys.exit(2)

    prev_agents = {}
    last_seen = {}  # id → last frame index
    teleports = []
    flickers = []
    ticks = []

    for i, f in enumerate(frames):
        data = json.loads(f.read_text())
        ticks.append(data['tick'])
        curr = {a['id']: (a['x'], a['y']) for a in data['agents']}
        for aid, (x, y) in curr.items():
            if aid in prev_agents:
                px, py = prev_agents[aid]
                d2 = (x - px) ** 2 + (y - py) ** 2
                if d2 > 8:
                    teleports.append((i, aid, d2, (px, py), (x, y)))
            if aid in last_seen and i - last_seen[aid] > 1:
                flickers.append((i, aid, last_seen[aid], i - last_seen[aid]))
            last_seen[aid] = i
        prev_agents = curr

    print(f'frames: {len(frames)}')
    print(f'ticks: min={min(ticks)} max={max(ticks)} delta={max(ticks) - min(ticks)}')
    print(f'teleports (dx²+dy² > 8): {len(teleports)}')
    for t in teleports[:5]:
        print(' ', t)
    print(f'flickers (id missing ≥ 1 frame): {len(flickers)}')
    for fl in flickers[:5]:
        print(' ', fl)

    # Exit nonzero if any anomalies found OR if the sim never advanced
    # (vacuous pass is still a failure signal for the QA gate).
    if teleports or flickers:
        sys.exit(1)
    if max(ticks) - min(ticks) < 3:
        print('WARNING: sim barely advanced during capture — gate failed')
        sys.exit(3)
    sys.exit(0)


if __name__ == '__main__':
    main()
