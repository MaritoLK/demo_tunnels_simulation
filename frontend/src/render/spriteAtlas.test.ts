import { vi, describe, it, expect, beforeAll } from 'vitest';

// The global vi.mock in setup.ts stubs spriteAtlas to a never-resolving
// loadSprites so the renderer tests don't try to fetch PNGs. This file
// undoes that locally so we can call the real loader against an Image
// stub. vi.doUnmock + vi.resetModules + dynamic import is the documented
// Vitest pattern for per-test un-mocking; vi.unmock hoists wrong here.

// Type-only imports (erased at runtime) — confirm the new types are
// exported from the module by name. A future rename of either union
// would fail tsc against this file even though no runtime assertion
// touches the types directly.
import type { ColonyPalette, PawnVariant, SpriteAtlas } from './spriteAtlas';

// Pin the union shapes via exhaustive-list assignment. If a member
// is dropped or renamed in the source, this file fails to compile.
const _allPalettes: readonly ColonyPalette[] = ['Red', 'Blue', 'Purple', 'Yellow'] as const;
const _allVariants: readonly PawnVariant[] = ['idle', 'run', 'idleMeat', 'runMeat'] as const;

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let mod: any;

beforeAll(async () => {
  // Stub HTMLImageElement so loadSprites resolves without real network.
  // The fake Image fires `onload` synchronously after `src` is set, which
  // is enough to drive the promise chain in loadImage / Promise.all.
  class FakeImage {
    onload: (() => void) | null = null;
    onerror: (() => void) | null = null;
    private _src = '';
    get src(): string { return this._src; }
    set src(v: string) {
      this._src = v;
      // Fire on next microtask so the await in loadImage observes a
      // promise-resolution rather than a synchronous re-entrant call.
      queueMicrotask(() => { this.onload?.(); });
    }
  }
  vi.stubGlobal('Image', FakeImage as unknown as typeof Image);

  vi.doUnmock('./spriteAtlas');
  vi.resetModules();
  mod = await import('./spriteAtlas');
});

describe('spriteAtlas shape', () => {
  it('exposes PAWN_FRAME_PX = 192', () => {
    expect(mod.PAWN_FRAME_PX).toBe(192);
  });

  it('declares all four ColonyPalette members', () => {
    expect(_allPalettes).toEqual(['Red', 'Blue', 'Purple', 'Yellow']);
  });

  it('declares all four PawnVariant members', () => {
    expect(_allVariants).toEqual(['idle', 'run', 'idleMeat', 'runMeat']);
  });

  it('loadSprites populates atlas.pawns with 4 palettes × 4 variants', async () => {
    const atlas: SpriteAtlas = await mod.loadSprites();
    for (const palette of _allPalettes) {
      for (const variant of _allVariants) {
        const img = atlas.pawns[palette][variant];
        expect(img, `pawns[${palette}][${variant}] should be defined`).toBeDefined();
      }
    }
  });

  it('legacy atlas.pawn aliases Blue idle for unmigrated callers', async () => {
    const atlas: SpriteAtlas = await mod.loadSprites();
    expect(atlas.pawn).toBe(atlas.pawns.Blue.idle);
  });
});
