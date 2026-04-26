import { describe, expect, it } from 'vitest';
import { FRAMES_PER_VARIANT, FRAME_MS } from './animConfig';

describe('FRAMES_PER_VARIANT', () => {
  // Tiny Swords' free pack ships idle sheets at 1536×192 (8 frames) but
  // run sheets at 1152×192 (6 frames). When the renderer cycled run
  // through 8 frames, frames 6 and 7 read past the source rect (srcX
  // up to 1390 vs sheet width 1152) and drawImage emitted transparent
  // pixels — the "agent disappears mid-walk" regression. Pinning each
  // count to the actual sheet dimensions stops that drift.
  it('idle and idleMeat use 8 frames (sheet 1536×192)', () => {
    expect(FRAMES_PER_VARIANT.idle).toBe(8);
    expect(FRAMES_PER_VARIANT.idleMeat).toBe(8);
  });

  it('run and runMeat use 6 frames (sheet 1152×192)', () => {
    expect(FRAMES_PER_VARIANT.run).toBe(6);
    expect(FRAMES_PER_VARIANT.runMeat).toBe(6);
  });

  it('FRAME_MS keeps the existing 10 fps cadence', () => {
    expect(FRAME_MS).toBe(100);
  });
});
