import { describe, it, expect } from 'vitest';
import { LifecycleFade, FADE_MS } from './lifecycleFade';

describe('LifecycleFade', () => {
  it('new id starts at alpha 0 and eases in to 1 over FADE_MS', () => {
    const f = new LifecycleFade();
    f.update({ present: new Set([1]), now: 1000 });
    expect(f.alphaFor(1, 1000)).toBeCloseTo(0, 3);
    expect(f.alphaFor(1, 1000 + FADE_MS / 2)).toBeGreaterThan(0.5);
    expect(f.alphaFor(1, 1000 + FADE_MS)).toBeCloseTo(1, 3);
    expect(f.alphaFor(1, 1000 + FADE_MS + 500)).toBe(1);
  });

  it('departed id fades from 1 to 0 and then reports undefined', () => {
    const f = new LifecycleFade();
    f.update({ present: new Set([1]), now: 0 });
    f.update({ present: new Set([1]), now: FADE_MS + 100 });
    expect(f.alphaFor(1, FADE_MS + 100)).toBe(1);
    f.update({ present: new Set<number>(), now: FADE_MS + 100 });
    expect(f.alphaFor(1, FADE_MS + 100)).toBeCloseTo(1, 3);
    expect(f.alphaFor(1, FADE_MS + 100 + FADE_MS / 2)).toBeLessThan(0.5);
    expect(f.alphaFor(1, FADE_MS + 100 + FADE_MS)).toBeCloseTo(0, 3);
    // After fade-out completes and we've pruned, the id is gone.
    f.update({ present: new Set<number>(), now: FADE_MS + 100 + FADE_MS + 1 });
    expect(f.has(1)).toBe(false);
  });

  it('lingering ids (still-present) return 1', () => {
    const f = new LifecycleFade();
    f.update({ present: new Set([1]), now: 0 });
    f.update({ present: new Set([1]), now: FADE_MS + 1000 });
    expect(f.alphaFor(1, FADE_MS + 1000)).toBe(1);
  });

  it('reappearing mid-fadeout snaps back to alive at alpha=1', () => {
    const f = new LifecycleFade();
    f.update({ present: new Set([1]), now: 0 });
    f.update({ present: new Set([1]), now: FADE_MS + 10 });      // alive
    f.update({ present: new Set<number>(), now: FADE_MS + 20 }); // start fade-out
    expect(f.alphaFor(1, FADE_MS + 20 + FADE_MS / 2)).toBeLessThan(0.5);
    f.update({ present: new Set([1]), now: FADE_MS + 30 });      // reappear
    expect(f.alphaFor(1, FADE_MS + 30)).toBe(1);
  });
});
