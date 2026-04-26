import { describe, it, expect } from 'vitest';
import { easeOutCubic } from './ease';

describe('easeOutCubic', () => {
  it('hits 0 at t=0', () => {
    expect(easeOutCubic(0)).toBe(0);
  });
  it('hits 1 at t=1', () => {
    expect(easeOutCubic(1)).toBe(1);
  });
  it('is past the midpoint at t=0.5 (biased toward arrival)', () => {
    const y = easeOutCubic(0.5);
    expect(y).toBeGreaterThan(0.8);
    expect(y).toBeLessThan(0.9);
  });
  it('clamps inputs outside [0,1]', () => {
    expect(easeOutCubic(-0.5)).toBe(0);
    expect(easeOutCubic(1.5)).toBe(1);
  });
});
