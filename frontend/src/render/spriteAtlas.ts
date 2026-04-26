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
// Crop overlay sprites — Bushe4 (leafy green) for the 'growing' state
// and Bushe3 (golden, denser canopy) for 'mature'. Same 1024×128 strip
// shape as bushUrl; we read frame 0 as a still pose. Replaced the
// previous green/yellow circles so crops feel like grown plants
// rather than pin-marker dots.
import cropGrowingUrl from '../assets/tiny-swords/free/Terrain/Decorations/Bushes/Bushe4.png';
import cropMatureUrl from '../assets/tiny-swords/free/Terrain/Decorations/Bushes/Bushe3.png';
import rockUrl from '../assets/tiny-swords/free/Terrain/Decorations/Rocks/Rock1.png';
// 4 colors × 4 variants = 16 explicit imports (Vite needs static URL
// strings; can't build import paths at runtime). Cargo-aware variants
// (Idle_Meat, Run_Meat) show the pawn carrying meat — visual feedback
// that cargo > 0.
import redIdleUrl       from '../assets/tiny-swords/free/Units/Red Units/Pawn/Pawn_Idle.png';
import redRunUrl        from '../assets/tiny-swords/free/Units/Red Units/Pawn/Pawn_Run.png';
import redIdleMeatUrl   from '../assets/tiny-swords/free/Units/Red Units/Pawn/Pawn_Idle Meat.png';
import redRunMeatUrl    from '../assets/tiny-swords/free/Units/Red Units/Pawn/Pawn_Run Meat.png';
import blueIdleUrl      from '../assets/tiny-swords/free/Units/Blue Units/Pawn/Pawn_Idle.png';
import blueRunUrl       from '../assets/tiny-swords/free/Units/Blue Units/Pawn/Pawn_Run.png';
import blueIdleMeatUrl  from '../assets/tiny-swords/free/Units/Blue Units/Pawn/Pawn_Idle Meat.png';
import blueRunMeatUrl   from '../assets/tiny-swords/free/Units/Blue Units/Pawn/Pawn_Run Meat.png';
import purpleIdleUrl     from '../assets/tiny-swords/free/Units/Purple Units/Pawn/Pawn_Idle.png';
import purpleRunUrl      from '../assets/tiny-swords/free/Units/Purple Units/Pawn/Pawn_Run.png';
import purpleIdleMeatUrl from '../assets/tiny-swords/free/Units/Purple Units/Pawn/Pawn_Idle Meat.png';
import purpleRunMeatUrl  from '../assets/tiny-swords/free/Units/Purple Units/Pawn/Pawn_Run Meat.png';
import yellowIdleUrl     from '../assets/tiny-swords/free/Units/Yellow Units/Pawn/Pawn_Idle.png';
import yellowRunUrl      from '../assets/tiny-swords/free/Units/Yellow Units/Pawn/Pawn_Run.png';
import yellowIdleMeatUrl from '../assets/tiny-swords/free/Units/Yellow Units/Pawn/Pawn_Idle Meat.png';
import yellowRunMeatUrl  from '../assets/tiny-swords/free/Units/Yellow Units/Pawn/Pawn_Run Meat.png';
// House sprites — 128×192 static per colony palette. Keyed by the
// backend colony name (Red / Blue / Purple / Yellow — see
// DEFAULT_COLONY_PALETTE in simulation_service.py). Three tiers per
// palette: House1 (founders' shack), Monastery (tier 1), Castle
// (tier 2). Indexed by colony.tier in the renderer. The user asked
// for the chained progression so the upgrade arc reads as a clear
// civilisation jump rather than three slightly-different cottages.
import houseRedT0Url from '../assets/tiny-swords/free/Buildings/Red Buildings/House1.png';
import houseRedT1Url from '../assets/tiny-swords/free/Buildings/Red Buildings/Monastery.png';
import houseRedT2Url from '../assets/tiny-swords/free/Buildings/Red Buildings/Castle.png';
import houseBlueT0Url from '../assets/tiny-swords/free/Buildings/Blue Buildings/House1.png';
import houseBlueT1Url from '../assets/tiny-swords/free/Buildings/Blue Buildings/Monastery.png';
import houseBlueT2Url from '../assets/tiny-swords/free/Buildings/Blue Buildings/Castle.png';
import housePurpleT0Url from '../assets/tiny-swords/free/Buildings/Purple Buildings/House1.png';
import housePurpleT1Url from '../assets/tiny-swords/free/Buildings/Purple Buildings/Monastery.png';
import housePurpleT2Url from '../assets/tiny-swords/free/Buildings/Purple Buildings/Castle.png';
import houseYellowT0Url from '../assets/tiny-swords/free/Buildings/Yellow Buildings/House1.png';
import houseYellowT1Url from '../assets/tiny-swords/free/Buildings/Yellow Buildings/Monastery.png';
import houseYellowT2Url from '../assets/tiny-swords/free/Buildings/Yellow Buildings/Castle.png';
// Tree / stump sprites for forest tiles. Tree1 is the leafy
// pre-chop sprite; Stump2 is the chopped variant drawn when the
// tile's wood resource has been depleted. Both 192×192 source
// frames; centred draw matches the bush overlay convention.
import treeUrl from '../assets/tiny-swords/free/Terrain/Resources/Wood/Trees/Tree1.png';
import stumpUrl from '../assets/tiny-swords/free/Terrain/Resources/Wood/Trees/Stump 2.png';

export type PawnVariant = 'idle' | 'run' | 'idleMeat' | 'runMeat';
export type ColonyPalette = 'Red' | 'Blue' | 'Purple' | 'Yellow';

export interface SpriteAtlas {
  tilemap: HTMLImageElement;
  water: HTMLImageElement;
  meat: HTMLImageElement;
  bush: HTMLImageElement;
  cropGrowing: HTMLImageElement;
  cropMature: HTMLImageElement;
  rock: HTMLImageElement;
  // Forest tile decorations. `tree` shows on a wood-bearing forest
  // tile (resource_amount > 0). `stump` replaces it once the tile
  // is fully chopped — paired with the depleted-tile traversability
  // change (forest underfoot is normally an extra-cost tile, but a
  // chopped tile becomes plain grass for movement purposes).
  tree: HTMLImageElement;
  stump: HTMLImageElement;
  // Deprecated — the old single-pawn field. Kept for compatibility with
  // any render path that hasn't migrated to the per-palette lookup yet;
  // points at Blue idle so behavior is unchanged.
  pawn: HTMLImageElement;
  pawns: Record<ColonyPalette, Record<PawnVariant, HTMLImageElement>>;
  // Per-palette house sprites indexed by tier. houses[name][tier] is
  // the rendered building for `colony.tier`. Three tiers today (0..2);
  // out-of-range tiers should clamp to MAX_TIER on the renderer side.
  houses: Record<string, HTMLImageElement[]>;
}

export const MAX_HOUSE_TIER = 2;

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

// House frame dimensions per tier. The Tiny Swords building sprites
// are NOT all the same size — House1 is 128×192 (2 tiles wide × 3
// tall), Monastery is 192×320 (3w × 5t), Castle is 320×256 (5w × 4t).
// Pre-fix the renderer hardcoded a single 128×192 sample rect for
// every tier so Monastery / Castle came back as a chopped corner of
// the upper-left, floating off the camp tile and visibly smaller
// than House1. Each entry below pairs the source-image dimensions
// (for the drawImage source rect) with the in-world footprint in
// tiles (for the destination rect). The renderer anchors each sprite
// bottom-center on the camp tile so the building's "front step" lines
// up regardless of which tier is showing.
export interface HouseTierDims {
  srcW: number;
  srcH: number;
  tilesW: number;
  tilesH: number;
}
export const HOUSE_TIER_DIMS: readonly HouseTierDims[] = [
  { srcW: 128, srcH: 192, tilesW: 2, tilesH: 3 },  // House1
  { srcW: 192, srcH: 320, tilesW: 3, tilesH: 5 },  // Monastery
  { srcW: 320, srcH: 256, tilesW: 5, tilesH: 4 },  // Castle
];

export async function loadSprites(): Promise<SpriteAtlas> {
  // Promise.all so all image loads run in parallel — first paint
  // is gated on the slowest, not the sum. loadPair returns a named
  // record (not a positional array) so a future field reorder can't
  // silently swap idle ↔ run via array-index drift.
  const loadPair = async (
    urls: Record<PawnVariant, string>,
  ): Promise<Record<PawnVariant, HTMLImageElement>> => {
    const [idle, run, idleMeat, runMeat] = await Promise.all([
      loadImage(urls.idle),
      loadImage(urls.run),
      loadImage(urls.idleMeat),
      loadImage(urls.runMeat),
    ]);
    return { idle, run, idleMeat, runMeat };
  };

  const loadHouseTriplet = async (
    urls: [string, string, string],
  ): Promise<HTMLImageElement[]> => {
    const [t0, t1, t2] = await Promise.all(urls.map(loadImage));
    return [t0, t1, t2];
  };

  const [
    tilemap, water, meat, bush, cropGrowing, cropMature, rock, tree, stump,
    redPawns, bluePawns, purplePawns, yellowPawns,
    redHouses, blueHouses, purpleHouses, yellowHouses,
  ] = await Promise.all([
    loadImage(tilemapUrl),
    loadImage(waterUrl),
    loadImage(meatUrl),
    loadImage(bushUrl),
    loadImage(cropGrowingUrl),
    loadImage(cropMatureUrl),
    loadImage(rockUrl),
    loadImage(treeUrl),
    loadImage(stumpUrl),
    loadPair({ idle: redIdleUrl,    run: redRunUrl,    idleMeat: redIdleMeatUrl,    runMeat: redRunMeatUrl }),
    loadPair({ idle: blueIdleUrl,   run: blueRunUrl,   idleMeat: blueIdleMeatUrl,   runMeat: blueRunMeatUrl }),
    loadPair({ idle: purpleIdleUrl, run: purpleRunUrl, idleMeat: purpleIdleMeatUrl, runMeat: purpleRunMeatUrl }),
    loadPair({ idle: yellowIdleUrl, run: yellowRunUrl, idleMeat: yellowIdleMeatUrl, runMeat: yellowRunMeatUrl }),
    loadHouseTriplet([houseRedT0Url, houseRedT1Url, houseRedT2Url]),
    loadHouseTriplet([houseBlueT0Url, houseBlueT1Url, houseBlueT2Url]),
    loadHouseTriplet([housePurpleT0Url, housePurpleT1Url, housePurpleT2Url]),
    loadHouseTriplet([houseYellowT0Url, houseYellowT1Url, houseYellowT2Url]),
  ]);

  return {
    tilemap, water, meat, bush, cropGrowing, cropMature, rock, tree, stump,
    // legacy single-pawn field = Blue idle (Task 11 retires this)
    pawn: bluePawns.idle,
    pawns: {
      Red: redPawns,
      Blue: bluePawns,
      Purple: purplePawns,
      Yellow: yellowPawns,
    },
    houses: {
      Red: redHouses,
      Blue: blueHouses,
      Purple: purpleHouses,
      Yellow: yellowHouses,
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
