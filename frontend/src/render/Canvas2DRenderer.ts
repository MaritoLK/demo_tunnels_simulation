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
  BUSH_FRAME_PX,
  HOUSE_FRAME_H,
  HOUSE_FRAME_W,
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
  // Tick-interpolation state. All of it lives on the renderer because
  // "how to fill the gap between two poll snapshots" is a rendering
  // concern, not a simulation one — the engine only hands us integer
  // tile positions.
  //   prevPositions      — agent positions at the last tick boundary;
  //                        lerped toward the snapshot's current position.
  //   lastSeenPositions  — rolling shadow of positions seen on the
  //                        most recent frame. Becomes prev on tick-advance.
  //   lastSeenTick       — most recent tick we drew (-1 = never).
  //   lastTickBoundaryAt — performance.now() when we last saw a tick advance.
  //   pollIntervalMs     — EMA of inter-poll delta, seeded from the React
  //                        Query poll interval. Controls lerp speed.
  private prevPositions = new Map<number, { x: number; y: number }>();
  private lastSeenPositions = new Map<number, { x: number; y: number }>();
  private lastSeenTick = -1;
  private lastTickBoundaryAt = 0;
  private pollIntervalMs = 500;

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
      width, height, tiles, agents, colonies, tilePx, cameraX, cameraY,
      selectedAgentId, reducedMotion, currentTick,
    } = snap;

    // Tick-advance bookkeeping for inter-poll interpolation. Runs
    // before any drawing so the agent loop below can read a consistent
    // (prevPositions, alpha) pair.
    const now = performance.now();
    const tickAdvanced = currentTick > this.lastSeenTick;
    if (tickAdvanced && this.lastSeenTick >= 0) {
      // Take the positions we drew last frame as the "prev" for this
      // tick, then measure how long the previous tick window actually
      // lasted so the lerp speed tracks real polling cadence.
      this.prevPositions = new Map(this.lastSeenPositions);
      const delta = now - this.lastTickBoundaryAt;
      // Bound the EMA: a laptop that sleeps for a minute shouldn't
      // pin the pollInterval at 60s. 3s covers 1 Hz sim speed with
      // plenty of slack; anything longer is dropped from the EMA —
      // pollIntervalMs keeps its last known value, not a reseed.
      // Consequence after a long sleep: the stale value persists
      // until the next sub-3s tick advance reseeds it. alpha clamps
      // to [0, 1] so the user never sees bogus positions — worst
      // case is one poll's worth of bodies pinned at target on wake,
      // then normal interpolation resumes. Explicit reseed via Page
      // Visibility listener considered and deferred: not observable
      // in demo conditions, more surface than the symptom justifies.
      if (delta > 0 && delta < 3000) {
        this.pollIntervalMs = this.pollIntervalMs * 0.7 + delta * 0.3;
      }
      this.lastTickBoundaryAt = now;
    } else if (this.lastSeenTick < 0) {
      // Very first frame — no history, no animation to unwind.
      this.lastTickBoundaryAt = now;
    }
    this.lastSeenTick = currentTick;

    // Prune dead/departed ids from both maps so there's no ghost draw
    // on subsequent frames and no slow memory bloat.
    const presentIds = new Set<number>();
    for (const a of agents) presentIds.add(a.id);
    for (const id of Array.from(this.lastSeenPositions.keys())) {
      if (!presentIds.has(id)) this.lastSeenPositions.delete(id);
    }
    for (const id of Array.from(this.prevPositions.keys())) {
      if (!presentIds.has(id)) this.prevPositions.delete(id);
    }

    const alpha = Math.max(0, Math.min(1, (now - this.lastTickBoundaryAt) / this.pollIntervalMs));

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

    // Camp markers — house sprite when atlas is loaded, colored square
    // fallback otherwise. Drawn above terrain so the camp reads as a
    // built object, below agents so the occupant covers their own tile.
    // The house is blitted oversized (2 tiles wide × 3 tall) and anchored
    // so its base sits on the camp tile — same pattern as pawns, so the
    // building stands on the ground rather than hovering over it.
    // Pulse factor: 0..1 sinusoid on wall-clock time, ~2s period. Same
    // `now` captured earlier this frame so the pulse ticks at refresh
    // rate without fighting the interp clock. Suppressed under
    // reducedMotion so a11y users don't get a throbber.
    const pulse = reducedMotion ? 0 : (Math.sin(now / 320) + 1) * 0.5;
    for (const colony of colonies) {
      const px = colony.camp_x * tilePx;
      const py = colony.camp_y * tilePx;
      // "Go-home" magnet ring — breathes around every camp so viewers
      // read the tile as a gravity well, not just a building. Drawn
      // BEFORE the house so the sprite covers the tile itself and the
      // ring flares outward. Anchored on the tile center, radius
      // modulated by the shared pulse.
      const campCx = px + tilePx / 2;
      const campCy = py + tilePx / 2;
      const baseR = tilePx * 0.85;
      const ringR = baseR + pulse * tilePx * 0.25;
      ctx.save();
      ctx.strokeStyle = colony.color;
      ctx.globalAlpha = 0.15 + pulse * 0.25;
      ctx.lineWidth = Math.max(1.5, tilePx * 0.08);
      ctx.beginPath();
      ctx.arc(campCx, campCy, ringR, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();
      const houseSprite = sprites ? sprites.houses[colony.name] : undefined;
      if (sprites && houseSprite) {
        const houseW = tilePx * 2;
        const houseH = tilePx * (HOUSE_FRAME_H / HOUSE_FRAME_W) * 2;
        const houseX = px + tilePx / 2 - houseW / 2;
        const houseY = py + tilePx - houseH;
        ctx.drawImage(
          houseSprite,
          0, 0, HOUSE_FRAME_W, HOUSE_FRAME_H,
          houseX, houseY, houseW, houseH,
        );
        // Thin colored halo ring under the house so team reading still
        // works even with the building obscuring the tile itself.
        ctx.strokeStyle = colony.color;
        ctx.lineWidth = Math.max(1.5, tilePx * 0.1);
        ctx.globalAlpha = 0.85;
        ctx.beginPath();
        ctx.ellipse(
          px + tilePx / 2, py + tilePx * 0.9,
          tilePx * 0.55, tilePx * 0.2,
          0, 0, Math.PI * 2,
        );
        ctx.stroke();
        ctx.globalAlpha = 1.0;
      } else {
        ctx.fillStyle = colony.color;
        ctx.globalAlpha = 0.9;
        ctx.fillRect(px + 2, py + 2, tilePx - 4, tilePx - 4);
        ctx.globalAlpha = 1.0;
        ctx.strokeStyle = 'rgba(0,0,0,0.6)';
        ctx.lineWidth = Math.max(1, tilePx * 0.06);
        ctx.strokeRect(px + 2, py + 2, tilePx - 4, tilePx - 4);
      }
    }

    // Crop overlay. Growing → small bush sprite at ~50% tile scale so a
    // sprout reads as a young plant, not a grass-colored dot colliding
    // with grass terrain. Mature → yellow fill dot (no asset in the free
    // pack conveys "ripe crop" better than a gold pip). Falls back to
    // the dot-pair in the procedural path for headless tests.
    for (let y = 0; y < height; y++) {
      const row = tiles[y];
      if (!row) continue;
      for (let x = 0; x < width; x++) {
        const t = row[x];
        if (!t || t.crop_state === 'none') continue;
        const ccx = x * tilePx + tilePx / 2;
        const ccy = y * tilePx + tilePx / 2;
        if (sprites && t.crop_state === 'growing') {
          const bushSize = tilePx * 0.55;
          const bushX = ccx - bushSize / 2;
          const bushY = ccy - bushSize / 2;
          ctx.drawImage(
            sprites.bush,
            0, 0, BUSH_FRAME_PX, BUSH_FRAME_PX,
            bushX, bushY, bushSize, bushSize,
          );
        } else {
          const cr = Math.max(2, tilePx * 0.22);
          ctx.fillStyle = t.crop_state === 'mature' ? '#f1c40f' : '#5cbd4a';
          ctx.beginPath();
          ctx.arc(ccx, ccy, cr, 0, Math.PI * 2);
          ctx.fill();
          ctx.strokeStyle = 'rgba(0,0,0,0.55)';
          ctx.lineWidth = Math.max(1, tilePx * 0.06);
          ctx.stroke();
        }
      }
    }

    // Colony color lookup — O(1) per agent in the loop below. Built once
    // per frame; colonies array is small (<=4) so this is negligible.
    const colonyColorById = new Map<number, string>();
    for (const c of colonies) colonyColorById.set(c.id, c.color);

    // Agent pass — rounded body with a subtle dark outline + glossy
    // highlight. Reads as little critter, not an abstract disc.
    for (const a of agents) {
      // Body position = interpolated between prev (last tick boundary)
      // and current (this tick's target). Halo + selection ring stay
      // on the target tile so hit-tests match the visual anchor.
      // Snap if the agent moved more than one tile in a single tick
      // window (teleport, multi-step tick batch) — sliding them
      // through intermediate tiles would look like they're phasing
      // through walls, worse than a crisp cut.
      const prev = this.prevPositions.get(a.id);
      let bodyX = a.x;
      let bodyY = a.y;
      if (prev && !reducedMotion) {
        const dx = a.x - prev.x;
        const dy = a.y - prev.y;
        if (dx * dx + dy * dy <= 2) {
          bodyX = prev.x + dx * alpha;
          bodyY = prev.y + dy * alpha;
        }
      }
      const cx = bodyX * tilePx + tilePx / 2;
      const cy = bodyY * tilePx + tilePx / 2;
      const targetCx = a.x * tilePx + tilePx / 2;
      const targetCy = a.y * tilePx + tilePx / 2;
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

      // Terrain-traversal feedback: backend sets state='traversing' while
      // the agent burns move_cooldown ticks on rough terrain (forest/sand/
      // stone). Render dust puffs beneath the feet so the pause reads as
      // "slowed by terrain" rather than "frozen bug". Drawn under the
      // body so the pawn silhouette stays crisp on top.
      const traversing = a.alive && a.state === 'traversing';
      if (traversing) {
        ctx.fillStyle = 'rgba(200,175,130,0.55)';
        for (const offset of [-0.45, 0, 0.45]) {
          ctx.beginPath();
          ctx.ellipse(
            cx + offset * r,
            cy + r * 0.55,
            r * 0.22,
            r * 0.14,
            0, 0, Math.PI * 2,
          );
          ctx.fill();
        }
      }

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
        } else if (traversing) {
          ctx.save();
          ctx.globalAlpha = 0.75;
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

      // Colony halo — a colored ring above the head says "this agent is
      // Red's". Applied to both sprite and procedural paths; the ring is
      // small and high so it doesn't fight the body silhouette.
      // Rogue agents: broken-dash ring in a desaturated tone — they've
      // lost their colony tie, so the visual should too.
      const colonyColor = a.colony_id != null ? colonyColorById.get(a.colony_id) : undefined;
      if (colonyColor) {
        ctx.save();
        if (a.rogue) {
          ctx.strokeStyle = 'rgba(140,140,150,0.7)';
          ctx.setLineDash([Math.max(2, tilePx * 0.1), Math.max(2, tilePx * 0.08)]);
        } else {
          ctx.strokeStyle = colonyColor;
        }
        ctx.lineWidth = Math.max(1.5, tilePx * 0.12);
        ctx.beginPath();
        ctx.arc(cx, cy - r * 0.4, r * 0.55, 0, Math.PI * 2);
        ctx.stroke();
        ctx.restore();
      }

      if (a.id === selectedAgentId) {
        const ringGap = Math.max(2, tilePx * 0.22);
        ctx.strokeStyle = '#ff7b3b';

        if (reducedMotion) {
          // Static selection ring — one solid coral circle, no halo,
          // no rotation. The user still needs to see which agent is
          // picked; motion is the only thing we drop. Ring pinned to
          // target tile (not lerped body) so it matches hit-tests.
          ctx.lineWidth = Math.max(1.5, tilePx * 0.12);
          ctx.setLineDash([]);
          ctx.beginPath();
          ctx.arc(targetCx, targetCy, r + ringGap, 0, Math.PI * 2);
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
          ctx.arc(targetCx, targetCy, r + ringGap + 4 + pulse * 3, 0, Math.PI * 2);
          ctx.fill();

          ctx.lineWidth = Math.max(1.5, tilePx * 0.12);

          // Rings anchor to the target tile, not the lerped body, so
          // the selection indicator matches the click hit-test region
          // instead of chasing the sprite across the interpolation
          // window.
          const dash = Math.max(2, tilePx * 0.18);
          ctx.save();
          ctx.translate(targetCx, targetCy);
          ctx.rotate(t * 0.6);
          ctx.setLineDash([dash, dash * 0.8]);
          ctx.beginPath();
          ctx.arc(0, 0, r + ringGap, 0, Math.PI * 2);
          ctx.stroke();
          ctx.restore();

          ctx.save();
          ctx.translate(targetCx, targetCy);
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

    // Fold the frame's positions into the rolling shadow map — next
    // tick-advance turns this into prevPositions.
    for (const a of agents) {
      this.lastSeenPositions.set(a.id, { x: a.x, y: a.y });
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
    this.prevPositions.clear();
    this.lastSeenPositions.clear();
    this.lastSeenTick = -1;
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
