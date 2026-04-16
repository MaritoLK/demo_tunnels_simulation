// Sprite atlas — single source of truth for which Tiny Swords PNG
// supplies which gameplay element. The renderer asks the atlas
// "where's the grass tile?" and gets back {sheet, sx, sy}, never a
// hard-coded pixel offset. Adding new terrain types or swapping a
// palette is a one-place change.
//
// Asset attribution: Tiny Swords by Pixel Frog
// (pixelfrog-assets.itch.io/tiny-swords) — free pack, commercial use
// permitted, attribution appreciated. Credited in the project README.
//
// Why imports, not <img src>: Vite resolves the import to a hashed URL
// at build time, so the asset is bundled, fingerprinted, and cache-
// busted on changes. No runtime file I/O, no 404 risk in prod.
import type { Terrain } from '../api/types';

// Tilemap sheet — 9 cols × 6 rows of 64×64 tiles. The top-left 3×3
// chunk is a "grass-on-water" autotile (centre + edges + corners).
import tilemapUrl from '../assets/tiny-swords/free/Terrain/Tileset/Tilemap_color1.png';
// Solid 64×64 water tile, tileable.
import waterUrl from '../assets/tiny-swords/free/Terrain/Tileset/Water Background color.png';
// Resource sprites — single-frame 64×64.
import meatUrl from '../assets/tiny-swords/free/Terrain/Resources/Meat/Meat Resource/Meat Resource.png';
// Decoration sprites — bushes are animated (1024×128 = 8 frames of
// 128×128, with the bush body centred and transparent padding around
// it), rocks are static 64×64. We use frame 0 of the bush for a
// still pose.
import bushUrl from '../assets/tiny-swords/free/Terrain/Decorations/Bushes/Bushe1.png';
import rockUrl from '../assets/tiny-swords/free/Terrain/Decorations/Rocks/Rock1.png';
// Pawn idle sheet — 1536×192 = 8 frames of 192×192. The pawn body
// occupies the lower-centre of each frame; the upper rows are
// animation overshoot space (head bob, tool sweep).
import pawnIdleUrl from '../assets/tiny-swords/free/Units/Blue Units/Pawn/Pawn_Idle.png';
// House sprites — 128×192 static per colony palette. Keyed by the
// backend colony name (Red / Blue / Purple / Yellow — see
// DEFAULT_COLONY_PALETTE in simulation_service.py). Drawn over the
// camp tile to give each colony a visible home.
import houseRedUrl from '../assets/tiny-swords/free/Buildings/Red Buildings/House1.png';
import houseBlueUrl from '../assets/tiny-swords/free/Buildings/Blue Buildings/House1.png';
import housePurpleUrl from '../assets/tiny-swords/free/Buildings/Purple Buildings/House1.png';
import houseYellowUrl from '../assets/tiny-swords/free/Buildings/Yellow Buildings/House1.png';

export interface SpriteAtlas {
  tilemap: HTMLImageElement;
  water: HTMLImageElement;
  meat: HTMLImageElement;
  bush: HTMLImageElement;
  rock: HTMLImageElement;
  pawn: HTMLImageElement;
  houses: Record<string, HTMLImageElement>;
}

// Source-image tile size. Distinct from the rendered tilePx — the
// renderer scales source 64s up to whatever zoom the camera uses.
export const SOURCE_TILE_PX = 64;

// Pawn idle frame is 192×192 (1536/8 = 192). The sprite body sits
// roughly in the central 96×96 region; the rest is animation slack.
export const PAWN_FRAME_PX = 192;

// Bush idle frame — 128×128, 8 frames horizontally. The visible bush
// is centred with transparent padding; reading a 64×64 quadrant loses
// most of the body, so always draw the full frame.
export const BUSH_FRAME_PX = 128;

// Where to read each engine terrain type from `tilemap`. Pixel offsets
// in the source PNG. For Tier 1 we map several terrains to the same
// centre-grass cell — visual variety comes later via decorations.
//
// Centre of the top-left 3×3 grass autotile = (col 1, row 1) in tile
// coords = (64, 64) in pixel coords. This is the fully-surrounded
// interior grass tile (no edges visible).
export const TERRAIN_TILE: Record<Terrain, { sx: number; sy: number }> = {
  grass:  { sx: 64, sy: 64 },
  forest: { sx: 64, sy: 64 }, // base; bush overlay drawn on top
  stone:  { sx: 64, sy: 64 }, // base; rock overlay drawn on top
  sand:   { sx: 64, sy: 64 }, // free pack has no sand tileset; flagged for Tier 3
  water:  { sx: 0,  sy: 0  }, // unused — water uses atlas.water sheet directly
};

// Decoration overlays per terrain. null = no overlay.
// Drawn after the base terrain tile, before resources and agents.
export const TERRAIN_DECORATION: Record<Terrain, 'bush' | 'rock' | null> = {
  grass:  null,
  forest: 'bush',
  stone:  'rock',
  sand:   null,
  water:  null,
};

// House frame is the full source image (128×192). The house body
// occupies the lower ~70% of the frame; drawing it so the base of
// the house anchors to the bottom of a ~3-tile-tall box sits the
// building plausibly "on" the camp tile instead of floating over it.
export const HOUSE_FRAME_W = 128;
export const HOUSE_FRAME_H = 192;

export async function loadSprites(): Promise<SpriteAtlas> {
  // Promise.all so all image loads run in parallel — first paint
  // is gated on the slowest, not the sum.
  const [
    tilemap, water, meat, bush, rock, pawn,
    houseRed, houseBlue, housePurple, houseYellow,
  ] = await Promise.all([
    loadImage(tilemapUrl),
    loadImage(waterUrl),
    loadImage(meatUrl),
    loadImage(bushUrl),
    loadImage(rockUrl),
    loadImage(pawnIdleUrl),
    loadImage(houseRedUrl),
    loadImage(houseBlueUrl),
    loadImage(housePurpleUrl),
    loadImage(houseYellowUrl),
  ]);
  return {
    tilemap, water, meat, bush, rock, pawn,
    houses: {
      Red: houseRed,
      Blue: houseBlue,
      Purple: housePurple,
      Yellow: houseYellow,
    },
  };
}

function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error(`spriteAtlas: failed to load ${url}`));
    img.src = url;
  });
}
