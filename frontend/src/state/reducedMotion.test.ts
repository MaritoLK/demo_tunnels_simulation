import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { isReducedMotion } from './reducedMotion';

// We promise in STUDY_NOTES §9.26 that every bit of motion in the app
// honours `prefers-reduced-motion: reduce`. CSS animations do — the
// canvas selection ring (rotating + breathing halo) does not, because
// the renderer reads `performance.now()` unconditionally. This helper
// is the gate: every motion path the renderer owns should branch on it.
//
// The helper is also deliberately server-safe: matchMedia is undefined
// in non-browser environments (SSR, tests without jsdom quirks). A
// defensive fallback to `false` is the right default — "assume motion
// is fine unless the OS says otherwise."
describe('isReducedMotion', () => {
  const originalMatchMedia = window.matchMedia;

  beforeEach(() => {
    // Clear any prior mock so each test starts from the real baseline.
    if (originalMatchMedia) {
      window.matchMedia = originalMatchMedia;
    }
  });

  afterEach(() => {
    if (originalMatchMedia) {
      window.matchMedia = originalMatchMedia;
    }
  });

  it('returns true when the OS reports reduce-motion preference', () => {
    window.matchMedia = vi.fn().mockReturnValue({ matches: true }) as typeof window.matchMedia;
    expect(isReducedMotion()).toBe(true);
  });

  it('returns false when the OS reports no reduce-motion preference', () => {
    window.matchMedia = vi.fn().mockReturnValue({ matches: false }) as typeof window.matchMedia;
    expect(isReducedMotion()).toBe(false);
  });

  it('queries the correct media string', () => {
    const spy = vi.fn().mockReturnValue({ matches: false });
    window.matchMedia = spy as typeof window.matchMedia;
    isReducedMotion();
    expect(spy).toHaveBeenCalledWith('(prefers-reduced-motion: reduce)');
  });

  it('returns false when matchMedia is unavailable (SSR / non-browser)', () => {
    // @ts-expect-error - intentionally removing matchMedia to simulate SSR
    delete window.matchMedia;
    expect(isReducedMotion()).toBe(false);
  });
});
