// Canvas2D implementation of Renderer.
//
// Scope/sizing: comfortably handles 100×100 tiles and ~100 moving agents
// at 60fps on modest hardware. Past that, the drawImage-per-tile cost
// dominates; the swap point is roughly "when the Chrome profiler shows
// >4ms in paint per frame" — at that point replace this file with a
// PixiJS adapter that uses sprite batching.
//
// Choices:
//   - Device-pixel-ratio scaling: set canvas.width to logical × DPR,
//     then ctx.scale(DPR, DPR). Otherwise every pixel is blurred on
//     retina displays. Common forgotten step, interview-quotable.
//   - imageSmoothingEnabled = false: pixel art must not be bilinear-
//     interpolated when scaled. Set in resize() and after each
//     ctx.save()/restore() pair preserves it automatically.
//   - Agents drawn last so they sit above terrain. Pawn sprite is
//     blitted oversized (2× tile) and bottom-anchored so head/tool
//     overshoot extends naturally above the unit's footprint.
//   - Selected agent gets a ring, not a sprite swap — colour/sprite
//     carry meaning (health/state), shouldn't be overloaded with
//     selection.
//   - Sprites load async via spriteAtlas.loadSprites(). Until ready,
//     we fall back to the procedural rect-based render so there's no
//     blank flash and tests don't require asset files.
import type { Renderer, FrameSnapshot } from './Renderer';
import type { Terrain } from '../api/types';
import {
  loadSprites,
  SOURCE_TILE_PX,
  TERRAIN_DECORATION,
  TERRAIN_TILE,
  type SpriteAtlas,
} from './spriteAtlas';

// Vivid WorldBox-inspired biome palette. Saturated, playful, reads as
// "sandbox world" not "scientific map." The canvas is the hero — chrome
// stays calm, the world pops. Each terrain gets a light/dark pair so we
// can paint a subtle inner tile pattern for texture without extra draws.
const TERRAIN_FILL: Record<Terrain, string> = {
  grass:  '#5cbd4a', // bright kelly-green, hero biome
  water:  '#2e8fc8', // saturated ocean blue
  forest: '#2d7c3a', // darker saturated green
  stone:  '#8a8a95', // cool stone grey
  sand:   '#e7c77a', // warm sandy yellow
};

// Slightly darker variant for each, painted as a speckle to break up
// the tile flatness. Gives the map a pixel-art-ish texture cheaply.
const TERRAIN_DARK: Record<Terrain, string> = {
  grass:  '#4ca83a',
  water:  '#2478b0',
  forest: '#226a2e',
  stone:  '#72727d',
  sand:   '#d4b462',
};

const RESOURCE_DOT_COLOUR: Record<string, string> = {
  food:  '#ff7b3b', // matches UI --hot coral — the "target" signal
  wood:  '#6b3e1a', // deep brown
  stone: '#d0d0d8', // light stone
};

export class Canvas2DRenderer implements Renderer {
  private host: HTMLElement | null = null;
  private canvas: HTMLCanvasElement | null = null;
  private ctx: CanvasRenderingContext2D | null = null;
  private dpr = 1;
  // Last dimensions actually applied to the backing store. The rAF
  // loop in WorldCanvas calls resize() every frame; assigning
  // canvas.width/height clears the backing store and resets all 2D
  // context state. Cache the last-applied (w, h) and skip no-ops so
  // steady-state frames are pure draws.
  private lastWidthPx = -1;
  private lastHeightPx = -1;
  // Sprite atlas — null until the async load resolves. Every draw
  // checks this and either uses sprites (when ready) or falls back to
  // the procedural rect renderer (during load, on load failure, in
  // tests where the assets aren't bundled).
  private sprites: SpriteAtlas | null = null;

  mount(host: HTMLElement): void {
    this.host = host;
    const canvas = document.createElement('canvas');
    canvas.style.display = 'block';
    canvas.style.imageRendering = 'pixelated';
    host.appendChild(canvas);
    this.canvas = canvas;
    const ctx = canvas.getContext('2d');
    if (!ctx) throw new Error('Canvas2D context unavailable');
    this.ctx = ctx;
    this.dpr = window.devicePixelRatio || 1;

    // Fire-and-forget load. The rAF loop polls `this.sprites` each
    // frame; when it flips from null to atlas, the next paint switches
    // automatically. No await — mount() returning a promise would force
    // the caller (WorldCanvas useEffect) into async-handling complexity
    // we don't need.
    loadSprites().then(
      (atlas) => { this.sprites = atlas; },
      (err) => {
        // Silent fallback: keep using procedural draw. Log so we know
        // why screenshots look different from expected.
        console.warn('[Canvas2DRenderer] sprite load failed; using procedural fallback', err);
      },
    );
  }

  resize(widthPx: number, heightPx: number): void {
    if (!this.canvas || !this.ctx) return;
    if (widthPx === this.lastWidthPx && heightPx === this.lastHeightPx) return;
    this.lastWidthPx = widthPx;
    this.lastHeightPx = heightPx;
    this.canvas.style.width = `${widthPx}px`;
    this.canvas.style.height = `${heightPx}px`;
    this.canvas.width = Math.floor(widthPx * this.dpr);
    this.canvas.height = Math.floor(heightPx * this.dpr);
    // Reset + scale so 1 unit = 1 CSS pixel regardless of DPR.
    this.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    this.ctx.imageSmoothingEnabled = false;
  }

  drawFrame(snap: FrameSnapshot): void {
    if (!this.canvas || !this.ctx) return;
    const { ctx } = this;
    const {
      width, height, tiles, agents, tilePx, cameraX, cameraY,
      selectedAgentId, reducedMotion,
    } = snap;

    ctx.save();
    // Background clear — match the shell ground so the canvas feels
    // continuous with the page when the world is smaller than the frame.
    ctx.fillStyle = '#0e1220';
    ctx.fillRect(0, 0, this.canvas.width / this.dpr, this.canvas.height / this.dpr);

    ctx.translate(cameraX, cameraY);

    // Terrain pass — sprite blit when the atlas is loaded, procedural
    // rect-fill as fallback. The two paths produce structurally similar
    // output (one tile per cell, resources on top); the sprite path is
    // just prettier.
    const sprites = this.sprites;
    for (let y = 0; y < height; y++) {
      const row = tiles[y];
      if (!row) continue;
      for (let x = 0; x < width; x++) {
        const tile = row[x];
        if (!tile) continue;
        const px = x * tilePx;
        const py = y * tilePx;

        if (sprites) {
          drawTerrainSprite(ctx, sprites, tile.terrain, px, py, tilePx);
          if (tile.resource_type === 'food' && tile.resource_amount > 0) {
            // Meat sprite for food, drawn at 50% tile centred so the
            // resource reads as "an item on the tile" rather than
            // dominating the whole cell. Full-tile meat looks like the
            // tile *is* meat — and at distance the chunky drumstick
            // silhouette reads as a T-rex head.
            const meatSize = tilePx * 0.5;
            const meatOffset = (tilePx - meatSize) / 2;
            ctx.drawImage(
              sprites.meat,
              0, 0, SOURCE_TILE_PX, SOURCE_TILE_PX,
              px + meatOffset, py + meatOffset, meatSize, meatSize,
            );
          }
          // Wood/stone: no overlay. The bush/rock decoration sprite
          // already communicates the resource; a dot on top produces
          // the "brown circle above tree / white circle on rock" bug
          // where the resource pip visually fights the decoration.
          // Dots are only for the procedural fallback path below.
        } else {
          // Procedural fallback — flat biome fill plus deterministic
          // corner speckle. Kept verbatim so tests and screenshots
          // remain consistent if sprite loading is disabled.
          ctx.fillStyle = TERRAIN_FILL[tile.terrain] ?? '#000';
          ctx.fillRect(px, py, tilePx, tilePx);
          const h = (x * 73856093) ^ (y * 19349663);
          if (((h >>> 0) & 0b11) !== 0 && tilePx >= 8) {
            ctx.fillStyle = TERRAIN_DARK[tile.terrain] ?? '#000';
            const sp = Math.max(1, Math.floor(tilePx * 0.22));
            const corner = (h >>> 2) & 0b11;
            const sx = px + (corner & 1 ? tilePx - sp - 1 : 1);
            const sy = py + (corner & 2 ? tilePx - sp - 1 : 1);
            ctx.fillRect(sx, sy, sp, sp);
          }
          if (tile.resource_type && tile.resource_amount > 0) {
            drawResourceDot(ctx, tile.resource_type, px, py, tilePx);
          }
        }
      }
    }

    // Agent pass — rounded body with a subtle dark outline + glossy
    // highlight. Reads as little critter, not an abstract disc.
    for (const a of agents) {
      const cx = a.x * tilePx + tilePx / 2;
      const cy = a.y * tilePx + tilePx / 2;
      // Floor at 4 CSS px so agents stay visible when the world is
      // auto-fit at a small zoom. Without a floor, a 40×25 world shown
      // at ~0.6 zoom renders agents as ~4-px dots that blur into the
      // resource pips — can't tell them apart at a glance.
      const r = Math.max(4, tilePx * 0.4);

      // Shadow on the ground tile for diorama depth.
      ctx.fillStyle = 'rgba(0,0,0,0.28)';
      ctx.beginPath();
      ctx.ellipse(cx, cy + r * 0.55, r * 0.9, r * 0.35, 0, 0, Math.PI * 2);
      ctx.fill();

      if (sprites) {
        // Tight crop on the pawn body inside the 192×192 frame. The
        // body lives at roughly (46, 30)–(146, 160) in source pixels —
        // the rest is animation-slack padding (head-bob + tool sweep
        // room). Drawing the whole frame at 1.5×tile scaled the body
        // down to 50% of the tile (visually invisible at fit-zoom).
        // Render the tight crop at native aspect: 1 tile wide × 1.3
        // tiles tall, foot anchored at tile bottom so only the head
        // overshoots upward.
        const srcX = 46, srcY = 30, srcW = 100, srcH = 130;
        const pawnW = tilePx;
        const pawnH = tilePx * (srcH / srcW);
        const pawnX = cx - pawnW / 2;
        const pawnY = cy + tilePx * 0.5 - pawnH;
        if (!a.alive) {
          ctx.save();
          ctx.globalAlpha = 0.35;
          ctx.drawImage(sprites.pawn, srcX, srcY, srcW, srcH, pawnX, pawnY, pawnW, pawnH);
          ctx.restore();
        } else {
          ctx.drawImage(sprites.pawn, srcX, srcY, srcW, srcH, pawnX, pawnY, pawnW, pawnH);
        }
      } else {
        // Procedural fallback body + outline + gloss highlight.
        ctx.fillStyle = a.alive ? healthColour(a.health) : '#3a3f55';
        ctx.beginPath();
        ctx.arc(cx, cy, r, 0, Math.PI * 2);
        ctx.fill();

        ctx.strokeStyle = 'rgba(0,0,0,0.45)';
        ctx.lineWidth = Math.max(1, tilePx * 0.08);
        ctx.stroke();

        ctx.fillStyle = 'rgba(255,255,255,0.35)';
        ctx.beginPath();
        ctx.arc(cx - r * 0.3, cy - r * 0.35, r * 0.35, 0, Math.PI * 2);
        ctx.fill();
      }

      if (a.id === selectedAgentId) {
        const ringGap = Math.max(2, tilePx * 0.22);
        ctx.strokeStyle = '#ff7b3b';

        if (reducedMotion) {
          // Static selection ring — one solid coral circle, no halo,
          // no rotation. The user still needs to see which agent is
          // picked; motion is the only thing we drop.
          ctx.lineWidth = Math.max(1.5, tilePx * 0.12);
          ctx.setLineDash([]);
          ctx.beginPath();
          ctx.arc(cx, cy, r + ringGap, 0, Math.PI * 2);
          ctx.stroke();
        } else {
          // Animated selection — two concentric dashed rings rotating
          // in opposite directions + a soft breathing halo. The inner
          // ring matches the body radius; the outer sits further out
          // so you can see the agent's own health colour through the
          // gap. `performance.now()` keys the animation; the renderer
          // stays a pure function of (snapshot, clock).
          const t = performance.now() / 1000;

          // Breathing halo — soft coral bloom pulsing with `sigil-pulse`
          // timing so the empty-state sigil and selection ring feel
          // like the same visual language.
          const pulse = 0.5 + 0.5 * Math.sin(t * 2.2);
          ctx.fillStyle = `rgba(255, 123, 59, ${0.08 + pulse * 0.12})`;
          ctx.beginPath();
          ctx.arc(cx, cy, r + ringGap + 4 + pulse * 3, 0, Math.PI * 2);
          ctx.fill();

          ctx.lineWidth = Math.max(1.5, tilePx * 0.12);

          // Outer dashed ring — rotates clockwise.
          const dash = Math.max(2, tilePx * 0.18);
          ctx.save();
          ctx.translate(cx, cy);
          ctx.rotate(t * 0.6);
          ctx.setLineDash([dash, dash * 0.8]);
          ctx.beginPath();
          ctx.arc(0, 0, r + ringGap, 0, Math.PI * 2);
          ctx.stroke();
          ctx.restore();

          // Inner solid ring — tighter, rotates counter-clockwise.
          ctx.save();
          ctx.translate(cx, cy);
          ctx.rotate(-t * 0.9);
          ctx.setLineDash([]);
          ctx.lineWidth = Math.max(1, tilePx * 0.08);
          ctx.beginPath();
          ctx.arc(0, 0, r + ringGap * 0.45, 0, Math.PI * 2);
          ctx.stroke();
          ctx.restore();
        }
      }
    }

    ctx.restore();
  }

  dispose(): void {
    if (this.canvas && this.host) this.host.removeChild(this.canvas);
    this.canvas = null;
    this.ctx = null;
    this.host = null;
    this.lastWidthPx = -1;
    this.lastHeightPx = -1;
  }
}

function healthColour(health: number): string {
  // Map 0..100 → red..green. Simple HSL interpolation.
  const h = Math.max(0, Math.min(120, (health / 100) * 120));
  return `hsl(${h}, 70%, 55%)`;
}

function drawTerrainSprite(
  ctx: CanvasRenderingContext2D,
  sprites: SpriteAtlas,
  terrain: Terrain,
  px: number,
  py: number,
  tilePx: number,
): void {
  if (terrain === 'water') {
    // Water has its own tileable sheet; tilemap.png water tiles are
    // edge variants meant for autotiling, not solid fill.
    ctx.drawImage(
      sprites.water,
      0, 0, SOURCE_TILE_PX, SOURCE_TILE_PX,
      px, py, tilePx, tilePx,
    );
    return;
  }
  if (terrain === 'sand') {
    // Free pack has no sand tileset (flagged for Tier 3). Until then,
    // a flat warm-yellow fill makes sand visually distinct from grass
    // — without this, sand tiles render as grass and the terrain is
    // a lie.
    ctx.fillStyle = '#e7c77a';
    ctx.fillRect(px, py, tilePx, tilePx);
    return;
  }
  // All non-water terrains share the centre-grass cell as a base;
  // the decoration overlay (bush/rock) is what visually distinguishes
  // forest from grass and stone from grass at Tier 1.
  const base = TERRAIN_TILE[terrain];
  ctx.drawImage(
    sprites.tilemap,
    base.sx, base.sy, SOURCE_TILE_PX, SOURCE_TILE_PX,
    px, py, tilePx, tilePx,
  );
  const decoration = TERRAIN_DECORATION[terrain];
  if (decoration === 'bush') {
    // Tight crop on the bush body inside the 128×128 frame. The
    // visible bush occupies roughly the central 96×96 region with
    // transparent padding around it — drawing the full frame at 1×1
    // tile wastes ~25% of the tile on padding, leaving the bush
    // smaller than the wood-resource dot and visually invisible at
    // fit-zoom. A tight 16,16,96,96 crop makes the bush fill the tile.
    ctx.drawImage(
      sprites.bush,
      16, 16, 96, 96,
      px, py, tilePx, tilePx,
    );
  } else if (decoration === 'rock') {
    ctx.drawImage(
      sprites.rock,
      0, 0, SOURCE_TILE_PX, SOURCE_TILE_PX,
      px, py, tilePx, tilePx,
    );
  }
}

function drawResourceDot(
  ctx: CanvasRenderingContext2D,
  resourceType: string,
  px: number,
  py: number,
  tilePx: number,
): void {
  const cx = px + tilePx / 2;
  const cy = py + tilePx / 2;
  const r = Math.max(2, tilePx * 0.22);
  ctx.fillStyle = RESOURCE_DOT_COLOUR[resourceType] ?? '#fff';
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = 'rgba(0,0,0,0.45)';
  ctx.lineWidth = Math.max(1, tilePx * 0.06);
  ctx.stroke();
}
