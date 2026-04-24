import { describe, it, expect } from 'vitest';
import { InterpBuffer, type Snap, type AgentSample } from './interpBuffer';

function snap(serverTimeMs: number, tick: number, agents: AgentSample[]): Snap {
  return { serverTimeMs, tick, agents };
}

describe('InterpBuffer', () => {
  it('returns targets exactly when renderTime matches a known snap', () => {
    const buf = new InterpBuffer();
    buf.push(snap(1000, 1, [{ id: 7, x: 0, y: 0 }]));
    buf.push(snap(2000, 2, [{ id: 7, x: 3, y: 0 }]));
    const out = buf.sampleAt(2000);
    expect(out.positions.get(7)).toEqual({ x: 3, y: 0, alphaRaw: 1 });
  });

  it('interpolates linearly between two snapshots', () => {
    const buf = new InterpBuffer();
    buf.push(snap(1000, 1, [{ id: 1, x: 0, y: 0 }]));
    buf.push(snap(2000, 2, [{ id: 1, x: 10, y: 0 }]));
    const out = buf.sampleAt(1500);
    const pos = out.positions.get(1)!;
    expect(pos.x).toBeCloseTo(5, 5);
    expect(pos.alphaRaw).toBeCloseTo(0.5, 5);
  });

  it('pins to older snap when renderTime is before buffer', () => {
    const buf = new InterpBuffer();
    buf.push(snap(1000, 1, [{ id: 1, x: 0, y: 0 }]));
    buf.push(snap(2000, 2, [{ id: 1, x: 10, y: 0 }]));
    const out = buf.sampleAt(500); // before
    expect(out.positions.get(1)).toEqual({ x: 0, y: 0, alphaRaw: 0 });
  });

  it('pins to newer snap when renderTime is past buffer', () => {
    const buf = new InterpBuffer();
    buf.push(snap(1000, 1, [{ id: 1, x: 0, y: 0 }]));
    buf.push(snap(2000, 2, [{ id: 1, x: 10, y: 0 }]));
    const out = buf.sampleAt(9000); // long after
    expect(out.positions.get(1)).toEqual({ x: 10, y: 0, alphaRaw: 1 });
  });

  it('keeps only last 2 snapshots', () => {
    const buf = new InterpBuffer();
    buf.push(snap(1000, 1, [{ id: 1, x: 0, y: 0 }]));
    buf.push(snap(2000, 2, [{ id: 1, x: 10, y: 0 }]));
    buf.push(snap(3000, 3, [{ id: 1, x: 20, y: 0 }]));
    // After third push, oldest (t=1000) is evicted. Interpolate 2→3.
    const out = buf.sampleAt(2500);
    expect(out.positions.get(1)!.x).toBeCloseTo(15, 5);
  });

  it('reports agents present in newer but not older as newlyPresent', () => {
    const buf = new InterpBuffer();
    buf.push(snap(1000, 1, [{ id: 1, x: 0, y: 0 }]));
    buf.push(snap(2000, 2, [{ id: 1, x: 10, y: 0 }, { id: 2, x: 5, y: 5 }]));
    const out = buf.sampleAt(1500);
    expect(out.newlyPresent).toContain(2);
    expect(out.positions.get(2)).toEqual({ x: 5, y: 5, alphaRaw: 1 });
  });

  it('reports agents present in older but not newer as departed', () => {
    const buf = new InterpBuffer();
    buf.push(snap(1000, 1, [{ id: 1, x: 0, y: 0 }, { id: 9, x: 9, y: 9 }]));
    buf.push(snap(2000, 2, [{ id: 1, x: 10, y: 0 }]));
    const out = buf.sampleAt(1500);
    expect(out.departed).toContain(9);
    // departed agent is pinned at its last-known position
    expect(out.positions.get(9)).toEqual({ x: 9, y: 9, alphaRaw: 1 });
  });
});
