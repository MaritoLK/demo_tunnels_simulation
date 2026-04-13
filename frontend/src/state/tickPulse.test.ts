import { describe, it, expect } from 'vitest';
import { nextTickPulseState } from './tickPulse';

// The HUD tick number flashes hot-coral for 420ms whenever the sim tick
// advances. The state transition is pure: given the previous observed
// tick and the current one, return whether to pulse and what to remember
// as the new "previous". Keeping it a function (instead of inlining in
// the effect) pins the invariant the original code missed: the
// "previous" ref must ALWAYS advance, even on the pulse path. Otherwise
// prev is frozen at the first observed value and the pulse check uses
// stale data — works by accident today, drifts silently when the tick
// sequence is ever non-monotonic (sim reset, error recovery).
describe('nextTickPulseState', () => {
  it('no pulse when both prev and curr are null (initial mount)', () => {
    expect(nextTickPulseState(null, null)).toEqual({ pulse: false, next: null });
  });

  it('no pulse on first observed tick (prev null)', () => {
    expect(nextTickPulseState(null, 0)).toEqual({ pulse: false, next: 0 });
  });

  it('pulses and advances prev when tick increments', () => {
    expect(nextTickPulseState(0, 1)).toEqual({ pulse: true, next: 1 });
  });

  it('no pulse when tick unchanged', () => {
    expect(nextTickPulseState(5, 5)).toEqual({ pulse: false, next: 5 });
  });

  it('pulses and advances prev on any change, including decrease (sim reset)', () => {
    expect(nextTickPulseState(100, 0)).toEqual({ pulse: true, next: 0 });
  });

  it('advances prev to null when sim data disappears (404 during polling)', () => {
    expect(nextTickPulseState(5, null)).toEqual({ pulse: false, next: null });
  });

  it('chained calls keep prev in sync across every tick', () => {
    let prev: number | null = null;
    const seen: Array<{ pulse: boolean; next: number | null }> = [];
    for (const t of [0, 1, 2, 3]) {
      const r = nextTickPulseState(prev, t);
      seen.push(r);
      prev = r.next;
    }
    // First call: prev=null, t=0 → no pulse, next=0
    // Then every step increments: pulse true, next=curr
    expect(seen).toEqual([
      { pulse: false, next: 0 },
      { pulse: true, next: 1 },
      { pulse: true, next: 2 },
      { pulse: true, next: 3 },
    ]);
  });
});
