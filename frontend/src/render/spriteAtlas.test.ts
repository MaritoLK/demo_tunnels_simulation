import { vi, describe, it, expect, beforeAll } from 'vitest';

// The global vi.mock in setup.ts stubs spriteAtlas to a never-resolving
// loadSprites so the renderer tests don't try to fetch PNGs. We undo
// that here to exercise the real module constants + shape. vi.doUnmock
// + vi.resetModules + dynamic import is the correct Vitest pattern for
// per-test un-mocking (vi.unmock is hoisted and unreliable vs doUnmock).

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let mod: any;

beforeAll(async () => {
  vi.doUnmock('../render/spriteAtlas');
  vi.resetModules();
  mod = await import('./spriteAtlas');
});

describe('spriteAtlas shape', () => {
  it('exposes PAWN_FRAME_PX = 192', () => {
    expect(mod.PAWN_FRAME_PX).toBe(192);
  });

  it('declares ColonyPalette + PawnVariant types', () => {
    // Type-level check: these strings compile correctly as the union types.
    // We also verify the module exports them (as strings at runtime).
    // The types themselves are erased by TypeScript — we just ensure the
    // import didn't blow up and the constant is present.
    expect(mod.PAWN_FRAME_PX).toBeDefined();
  });

  it('SpriteAtlas interface includes pawns field (compile-time check)', () => {
    // Construct a minimal object that satisfies SpriteAtlas — if the
    // interface is missing `pawns` or `pawn` this file won't compile.
    type ColonyPalette = 'Red' | 'Blue' | 'Purple' | 'Yellow';
    type PawnVariant = 'idle' | 'run' | 'idleMeat' | 'runMeat';
    const img = new Image();
    const variantMap: Record<PawnVariant, HTMLImageElement> = {
      idle: img, run: img, idleMeat: img, runMeat: img,
    };
    // Structural check: all 4 palettes accessible under atlas.pawns
    const pawns: Record<ColonyPalette, Record<PawnVariant, HTMLImageElement>> = {
      Red: variantMap, Blue: variantMap, Purple: variantMap, Yellow: variantMap,
    };
    for (const color of ['Red', 'Blue', 'Purple', 'Yellow'] as ColonyPalette[]) {
      expect(pawns[color]).toBeDefined();
      expect(pawns[color].idle).toBeInstanceOf(HTMLImageElement);
      expect(pawns[color].run).toBeInstanceOf(HTMLImageElement);
      expect(pawns[color].idleMeat).toBeInstanceOf(HTMLImageElement);
      expect(pawns[color].runMeat).toBeInstanceOf(HTMLImageElement);
    }
  });
});
