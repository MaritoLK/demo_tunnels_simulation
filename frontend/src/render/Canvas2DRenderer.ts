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
import { CARRY_MAX, type Terrain } from '../api/types';
import {
  HOUSE_FRAME_H,
  HOUSE_FRAME_W,
  loadSprites,
  PAWN_FRAME_PX,
  SOURCE_TILE_PX,
  TERRAIN_DECORATION,
  TERRAIN_TILE,
  type ColonyPalette,
  type PawnVariant,
  type SpriteAtlas,
} from './spriteAtlas';
import { FRAME_MS, FRAMES_PER_VARIANT, STATE_VISUALS } from './animConfig';
import { InterpBuffer } from './interpBuffer';
import { LifecycleFade } from './lifecycleFade';

interface AnimState {
  variant: PawnVariant;
  frameIndex: number;
  elapsedMs: number;
}

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

// Below this tile size the label is unreadable and just adds clutter.
// Matched to the food-badge threshold (≥14 CSS px) so both overlays
// appear/disappear at the same zoom level.
const LABEL_MIN_TILE_PX = 14;

// How long a d20 forage chip stays on screen above the rolling agent.
// 1500 ms is long enough for the eye to land on the number and parse
// "1d20 = N" before it fades, short enough that two consecutive rolls
// from the same agent don't stack visually. Chip alpha lerps to 0 over
// the window so the disappearance reads as a fade, not a snap.
const DICE_CHIP_DURATION_MS = 1500;

/**
 * Pick the pawn animation variant for `agent`. Motion comes from
 * position delta (not state string) — the engine's STATE_FORAGING
 * is set both when gathering in place AND when stepping toward food,
 * so a state-based motion check would lope motionless foragers.
 */
export function pickVariant(
  agent: { state: string; cargo?: number; x: number; y: number },
  prev: { x: number; y: number } | undefined,
): PawnVariant {
  const moving = prev !== undefined && (agent.x !== prev.x || agent.y !== prev.y);
  const carrying = (agent.cargo ?? 0) > 0;
  if (moving && carrying) return 'runMeat';
  if (moving) return 'run';
  if (carrying) return 'idleMeat';
  return 'idle';
}

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
  // Interpolation + lifecycle state — delegated to purpose-built classes.
  //   interpBuffer    — 2-snapshot ring; sampleAt(renderTimeMs) produces
  //                     per-agent interpolated positions.
  //   fade            — per-agent in/alive/out lifecycle, drives alpha.
  //   lastFrameSample — positions produced by the most recent sampleAt call;
  //                     used by the anim-state loop next frame to detect
  //                     motion (run vs idle variant). Replaces prevPositions.
  private interpBuffer = new InterpBuffer();
  private fade = new LifecycleFade();
  private lastFrameSample: Map<number, { x: number; y: number }> = new Map();
  // Per-agent animation state — lazily created on first sight.
  // Swept at end of each draw so departed/dead agents don't accumulate.
  private animStates: Map<number, AnimState> = new Map();
  // Wall-clock time of the previous drawFrame call — used to compute dt
  // for frame-cycling. 0 on first frame (dt = 0, no advance).
  private lastFrameAt = 0;

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

  /** Push a new server snapshot into the interpolation buffer.
   *  Called by WorldCanvas whenever a stream or poll snapshot arrives.
   *
   *  The buffer is keyed in CLIENT receive time (`performance.now()`),
   *  not server clock. Server time is frozen between snaps, so anchoring
   *  the renderer's sample clock to it left the interp fraction stuck —
   *  agents teleported to the latest position the moment a snap arrived
   *  and then sat still until the next one. Client time advances 1 ms
   *  per 1 ms, so a sample clock derived from `performance.now()` walks
   *  smoothly between snaps and the agent actually walks the tile. */
  ingestSnapshot(snap: { serverTimeMs: number; tick: number; agents: Array<{ id: number; x: number; y: number }> }): void {
    this.interpBuffer.push({
      serverTimeMs: performance.now(),
      tick: snap.tick,
      agents: snap.agents,
    });
  }

  drawFrame(snap: FrameSnapshot): void {
    if (!this.canvas || !this.ctx) return;
    const { ctx } = this;
    const {
      width, height, tiles, agents, colonies, tilePx, cameraX, cameraY,
      selectedAgentId, selectedTile, reducedMotion, recentForageRolls,
    } = snap;

    // Sample the interpolation buffer one tick interval behind `now`, so
    // sampleTime walks from the older snap's receive time forward to the
    // newer's at 1 ms/ms. INTERP_DELAY adapts to the observed snap gap
    // (≈ tick interval at the current sim speed) — keeps t in [0, 1]
    // across the full interval so the agent is animating every frame
    // instead of pinned at the head of each tick. Falls back to a
    // single-tick default while the buffer is still warming.
    const now = performance.now();
    const INTERP_DELAY_FALLBACK_MS = 250;
    const interpDelayMs = this.interpBuffer.lastSnapInterval() ?? INTERP_DELAY_FALLBACK_MS;
    const sampleTimeMs = now - interpDelayMs;
    const sample = this.interpBuffer.sampleAt(sampleTimeMs);

    // Present ids = whoever the buffer is producing a position for
    // (includes departed-and-pinned). LifecycleFade decides fade state.
    const presentIds = new Set<number>();
    for (const id of sample.positions.keys()) presentIds.add(id);
    this.fade.update({ present: presentIds, now });

    // Frame-cycling: compute dt from wall-clock delta between drawFrame calls.
    // dt = 0 on the very first frame (lastFrameAt = 0) so no phantom advance.
    const dt = this.lastFrameAt > 0 ? now - this.lastFrameAt : 0;
    this.lastFrameAt = now;

    // Per-agent anim state — pick variant + advance frameIndex at 10 fps.
    // Must run before the agent draw loop (below) which reads animStates.
    for (const agent of agents) {
      if (!agent.alive) continue;
      const prev = this.lastFrameSample.get(agent.id);
      const wantVariant = pickVariant(agent, prev);

      let anim = this.animStates.get(agent.id);
      if (!anim || anim.variant !== wantVariant) {
        // New agent or variant change: reset to frame 0.
        anim = { variant: wantVariant, frameIndex: 0, elapsedMs: 0 };
        this.animStates.set(agent.id, anim);
      } else {
        anim.elapsedMs += dt;
        while (anim.elapsedMs >= FRAME_MS) {
          anim.frameIndex = (anim.frameIndex + 1) % FRAMES_PER_VARIANT[anim.variant];
          anim.elapsedMs -= FRAME_MS;
        }
      }
    }

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
            // Food-unit badge — shows the tile's raw resource_amount
            // so the number matches what the TilePanel reads out. An
            // earlier revision counted "servings" (amount/FORAGE_SERVING),
            // but that made a 9-unit tile show ×5, which looked like a
            // bug every time someone opened the panel. Tile sprites now
            // count down 1-for-1 with forages.
            const units = Math.ceil(tile.resource_amount);
            if (units >= 2 && tilePx >= 14) {
              drawFoodBadge(ctx, units, px, py, tilePx);
            }
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

    // Fog of war veil. Each colony tracks its own `explored` set
    // (engine-side, reset at dusk → night). The renderer takes the
    // union so any colony's reveal counts as "the player's view" for
    // this demo — per-colony toggling is a later feature. Cells that
    // no colony has touched render as opaque shell-color so the world
    // beyond the agents' reach looks unknown rather than lit-but-empty.
    // Drawn after terrain and before camps/crops/agents — by
    // construction those layers all sit on tiles their owning colony
    // has revealed, so the veil never covers a camp / crop / agent.
    const exploredCells = new Set<number>();
    for (const c of colonies) {
      if (!c.explored) continue;
      for (const [x, y] of c.explored) {
        exploredCells.add(y * width + x);
      }
    }
    if (exploredCells.size > 0) {
      // Skip the pass when the engine hasn't sent fog yet (older client
      // / first-tick race) so the world isn't all-dark before the first
      // reveal lands.
      ctx.fillStyle = '#0e1220';
      for (let y = 0; y < height; y++) {
        for (let x = 0; x < width; x++) {
          if (exploredCells.has(y * width + x)) continue;
          ctx.fillRect(x * tilePx, y * tilePx, tilePx, tilePx);
        }
      }
    }

    // Wolves marker — draw a 🐺 glyph on revealed wolves tiles so the
    // player can SEE the hazard once discovered. Hidden behind fog by
    // construction (we only iterate explored cells in this pass), so
    // wolves only become visible after a colony has scouted that tile.
    // Drawn after fog and before crops/camps/agents so the marker sits
    // in the world layer, not on top of the colony's units.
    if (exploredCells.size > 0) {
      ctx.font = `${Math.max(12, Math.floor(tilePx * 0.65))}px system-ui, sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      for (let y = 0; y < height; y++) {
        const rowTiles = tiles[y];
        if (!rowTiles) continue;
        for (let x = 0; x < width; x++) {
          if (!exploredCells.has(y * width + x)) continue;
          const t = rowTiles[x];
          if (!t || !t.wolves) continue;
          ctx.fillText('🐺', x * tilePx + tilePx / 2, y * tilePx + tilePx / 2);
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

    // Crop overlay — paired dots, same style across states:
    //   growing → green dot (planted, not yet ripe)
    //   mature  → yellow dot (harvestable)
    // Earlier revisions drew a bush sprite for 'growing' when the atlas
    // was loaded, but the sprite collided visually with wild bush
    // decorations on forest tiles. Uniform-dot style (green↔yellow)
    // reads like a simple state change rather than two different things.
    for (let y = 0; y < height; y++) {
      const row = tiles[y];
      if (!row) continue;
      for (let x = 0; x < width; x++) {
        const t = row[x];
        if (!t || t.crop_state === 'none') continue;
        const ccx = x * tilePx + tilePx / 2;
        const ccy = y * tilePx + tilePx / 2;
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

    // Tile selection ring — drawn between tile sprites and agents so a
    // pawn standing on the selected tile stays readable on top of the
    // ring. Dashed square with a soft inner glow; size tracks tilePx
    // so it reads at any zoom that allows it.
    if (selectedTile) {
      // Inside the camera translate (see ctx.translate(cameraX,cameraY)
      // earlier in drawFrame), so world-space tile coords suffice — no
      // camera offset here or the ring lands off by (cameraX, cameraY).
      const tx = selectedTile.x * tilePx;
      const ty = selectedTile.y * tilePx;
      ctx.save();
      ctx.lineWidth = Math.max(2, tilePx * 0.06);
      ctx.strokeStyle = '#ffd23f';
      ctx.setLineDash([Math.max(4, tilePx * 0.15), Math.max(3, tilePx * 0.1)]);
      const inset = Math.max(2, tilePx * 0.08);
      ctx.strokeRect(tx + inset, ty + inset, tilePx - inset * 2, tilePx - inset * 2);
      ctx.setLineDash([]);
      ctx.restore();
    }

    // Colony lookup — O(1) per agent in the loop below. Built once
    // per frame; colonies array is small (<=4) so this is negligible.
    // The full colony object is needed for both .color (existing) and
    // .sprite_palette (Task 11 palette-aware pawn draw); a single map
    // avoids two parallel `find` calls.
    const colonyById = new Map<number, typeof colonies[number]>();
    for (const c of colonies) colonyById.set(c.id, c);

    // Agent pass — rounded body with a subtle dark outline + glossy
    // highlight. Reads as little critter, not an abstract disc.
    for (const a of agents) {
      // Body position: use InterpBuffer sample when motion is enabled.
      // reducedMotion bypasses the buffer entirely — draw at the exact
      // server-reported tile. LifecycleFade drives alpha (fade in/out).
      const p = sample.positions.get(a.id);
      const reducedBypass = reducedMotion;
      const bodyX = reducedBypass ? a.x : (p?.x ?? a.x);
      const bodyY = reducedBypass ? a.y : (p?.y ?? a.y);
      const lifecycleAlpha = this.fade.alphaFor(a.id, now);
      const cx = bodyX * tilePx + tilePx / 2;
      const cy = bodyY * tilePx + tilePx / 2;
      const targetCx = a.x * tilePx + tilePx / 2;
      const targetCy = a.y * tilePx + tilePx / 2;
      // Floor at 4 CSS px so agents stay visible when the world is
      // auto-fit at a small zoom. Without a floor, a 40×25 world shown
      // at ~0.6 zoom renders agents as ~4-px dots that blur into the
      // resource pips — can't tell them apart at a glance.
      const r = Math.max(4, tilePx * 0.4);

      // One outer save/restore per agent so lifecycleAlpha applies to
      // the whole stack — body, shadow, halo, label, cargo pip, state
      // icon, selection ring. Without this, only the body sprite/disc
      // faded in/out and the overlays stayed fully opaque, producing
      // ~250 ms of "ghost body with hovering opaque label" right after
      // sim load. The body block's own save/restore composes fine: it
      // overwrites globalAlpha (e.g. 0.35 * lifecycleAlpha for dead),
      // then restores back to lifecycleAlpha — overlays inherit it.
      ctx.save();
      ctx.globalAlpha = lifecycleAlpha;

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
        // Palette-aware per-variant per-frame pawn draw.
        // Each pawn sheet is 1536×192 = 8 frames of PAWN_FRAME_PX×PAWN_FRAME_PX.
        // The anim state was set for alive agents in the frame-cycling block above.
        // Dead agents skip the anim state (not alive → not in animStates) so
        // fall back to the colony palette's idle sheet at frame 0.
        //
        // Tight crop: body lives at roughly (46,30)–(146,160) in the 192×192 frame.
        // Drawing the whole 192×192 at 1×tile leaves the body at 52% of tile width.
        // Crop to (100×130) at the correct frame-horizontal offset so it fills 1 tile.
        const colony = a.colony_id != null ? colonyById.get(a.colony_id) : undefined;
        const palette = (colony?.sprite_palette as ColonyPalette | undefined) ?? 'Blue';
        const palettePawns = sprites.pawns[palette] ?? sprites.pawns.Blue;
        const anim = a.alive ? this.animStates.get(a.id) : undefined;
        const variant: PawnVariant = anim?.variant ?? 'idle';
        const sheet = palettePawns[variant];
        const frameIndex = anim?.frameIndex ?? 0;
        // Source: crop the body from the correct animation frame column.
        // Within-frame body crop: (46, 30) to (146, 160) = 100×130 px.
        const srcX = frameIndex * PAWN_FRAME_PX + 46;
        const srcY = 30, srcW = 100, srcH = 130;
        const pawnW = tilePx;
        const pawnH = tilePx * (srcH / srcW);
        const pawnX = cx - pawnW / 2;
        const pawnY = cy + tilePx * 0.5 - pawnH;
        ctx.save();
        if (!a.alive) ctx.globalAlpha = 0.35 * lifecycleAlpha;
        else if (traversing) ctx.globalAlpha = 0.75 * lifecycleAlpha;
        else ctx.globalAlpha = lifecycleAlpha;
        ctx.drawImage(sheet, srcX, srcY, srcW, srcH, pawnX, pawnY, pawnW, pawnH);
        ctx.restore();
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

      // State icon overlay — small glyph above the pawn. Skip when state's
      // glyph is empty (default for 'idle' = nothing to say). Phase = current
      // day/night phase from snap; falls back to 'day' if missing.
      const pawnTopY = sprites && a.alive
        ? cy + tilePx * 0.5 - tilePx * (130 / 100)  // sprite path pawnY
        : cy - r;  // procedural path approximate top
      this._drawStateIcon(ctx, a.state, cx, pawnTopY, snap.phase ?? 'day');

      // Cargo pip — small brown satchel at top-right of the pawn when
      // the agent is carrying anything. Radius scales with fullness
      // (minimum visible even at 1 unit, max at CARRY_MAX) so the
      // pouch visibly "swells" between forage and deposit. Skipped
      // for dead agents — corpses don't haul.
      const cargo = a.alive ? a.cargo ?? 0 : 0;
      if (cargo > 0) {
        const fill = Math.min(1, cargo / CARRY_MAX);
        const pipR = Math.max(2, r * (0.18 + 0.22 * fill));
        const pipCx = cx + r * 0.55;
        const pipCy = cy - r * 0.55;
        ctx.fillStyle = '#6b3e1a';
        ctx.beginPath();
        ctx.arc(pipCx, pipCy, pipR, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = 'rgba(0,0,0,0.55)';
        ctx.lineWidth = Math.max(1, tilePx * 0.05);
        ctx.stroke();
      }

      // Colony halo — a colored ring above the head says "this agent is
      // Red's". Applied to both sprite and procedural paths; the ring is
      // small and high so it doesn't fight the body silhouette.
      // Rogue agents: broken-dash ring in a desaturated tone — they've
      // lost their colony tie, so the visual should too.
      const colonyColor = a.colony_id != null ? colonyById.get(a.colony_id)?.color : undefined;
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

      // Action label — one short, color-coded word floating above the
      // head. Lets a viewer see "the Blue colony is all foraging" at a
      // glance without selecting each pawn. Drawn as stroke-then-fill
      // so the text stays legible over any terrain (forest, sand, and
      // the pawn sprite itself all compete for contrast). Skip dead
      // agents (their fade already says "stopped") and skip when the
      // tile is too small to render a readable glyph.
      const meta = a.alive ? STATE_VISUALS[a.state] : undefined;
      if (meta?.label && meta.color && tilePx >= LABEL_MIN_TILE_PX) {
        // Anchor above the colony halo: halo sits at cy - r*0.4 with
        // radius r*0.55, so its top is cy - 0.95*r. Labels at cy - 1.4*r
        // clear the halo by ~0.45r and don't collide with the cargo pip
        // (top-right at cy - 0.55r).
        const fontPx = Math.max(9, Math.floor(tilePx * 0.34));
        ctx.font = `600 ${fontPx}px system-ui, sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'alphabetic';
        const labelY = cy - r * 1.4;
        ctx.lineWidth = Math.max(2, tilePx * 0.09);
        ctx.strokeStyle = 'rgba(10,12,18,0.85)';
        ctx.strokeText(meta.label, cx, labelY);
        ctx.fillStyle = meta.color;
        ctx.fillText(meta.label, cx, labelY);
      }

      // d20 dice chip — flashes the most recent forage roll above the
      // agent for DICE_CHIP_DURATION_MS, fading to zero alpha by the
      // end of the window. Crit (20) and crit-fail (1) get distinct
      // tints so the rare beats read at a glance without needing a
      // legend. Drawn above the state label (cy - r*2.0) so it doesn't
      // collide with the action word.
      const rollEntry = recentForageRolls?.get(a.id);
      if (rollEntry && tilePx >= LABEL_MIN_TILE_PX) {
        const elapsed = now - rollEntry.receivedAtMs;
        if (elapsed >= 0 && elapsed < DICE_CHIP_DURATION_MS) {
          const fade = 1 - elapsed / DICE_CHIP_DURATION_MS;
          let chipColor = '#ffffff';
          if (rollEntry.roll === 1) chipColor = '#ff5555';
          else if (rollEntry.roll === 20) chipColor = '#ffd23f';
          const fontPx = Math.max(10, Math.floor(tilePx * 0.36));
          ctx.font = `700 ${fontPx}px system-ui, sans-serif`;
          ctx.textAlign = 'center';
          ctx.textBaseline = 'alphabetic';
          const chipY = cy - r * 2.0;
          const text = `🎲 ${rollEntry.roll}`;
          ctx.save();
          ctx.globalAlpha *= fade;
          ctx.lineWidth = Math.max(2, tilePx * 0.1);
          ctx.strokeStyle = 'rgba(10,12,18,0.85)';
          ctx.strokeText(text, cx, chipY);
          ctx.fillStyle = chipColor;
          ctx.fillText(text, cx, chipY);
          ctx.restore();
        }
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
      ctx.restore();
    }

    // Snapshot the interpolated positions so next frame's anim-state loop
    // can detect motion (run vs idle variant) via lastFrameSample.
    this.lastFrameSample.clear();
    for (const [id, pos] of sample.positions) {
      this.lastFrameSample.set(id, { x: pos.x, y: pos.y });
    }

    // Sweep departed agents from animStates to prevent unbounded growth.
    // Includes corpses still in the snapshot (agent.alive==false) — but
    // those never entered animStates anyway (anim-advance loop skips dead),
    // so the delete on a present-but-corpse id is a harmless no-op.
    // Variable named distinctly from the `presentIds` set used earlier
    // for the prevPositions sweep — same concept, different lifecycle.
    const animPresentIds = new Set(agents.map(a => a.id));
    for (const id of Array.from(this.animStates.keys())) {
      if (!animPresentIds.has(id)) this.animStates.delete(id);
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
    this.lastFrameSample.clear();
    this.animStates.clear();
    this.lastFrameAt = 0;
  }

  private _drawStateIcon(
    ctx: CanvasRenderingContext2D,
    state: string,
    cx: number,
    baseY: number,
    phase: string,
  ): void {
    const glyph = STATE_VISUALS[state]?.glyph ?? '';
    if (!glyph) return;                   // draw-guard — no fillText('')
    ctx.save();
    // Compose night-dim with whatever alpha the caller already pushed
    // (lifecycleAlpha at the per-agent wrap, or 1.0 outside it). A bare
    // assignment would clobber the lifecycle fade and snap the icon to
    // full opacity even while its agent is still fading in.
    if (phase === 'night') ctx.globalAlpha *= 0.4;
    ctx.font = '18px system-ui, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillStyle = '#ffffff';
    ctx.fillText(glyph, cx, baseY - 18);
    ctx.restore();
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

// "×N" badge in the bottom-right of the food tile, so the player can
// see the stack shrink forage-by-forage rather than wait for the whole
// sprite to disappear on the last serving.
function drawFoodBadge(
  ctx: CanvasRenderingContext2D,
  servings: number,
  px: number,
  py: number,
  tilePx: number,
): void {
  const label = `×${servings}`;
  const fontPx = Math.max(9, Math.floor(tilePx * 0.32));
  ctx.font = `700 ${fontPx}px system-ui, sans-serif`;
  ctx.textAlign = 'right';
  ctx.textBaseline = 'bottom';
  const tx = px + tilePx - Math.max(2, tilePx * 0.08);
  const ty = py + tilePx - Math.max(2, tilePx * 0.06);
  // Outline first so the digits read against any terrain tint.
  ctx.lineWidth = Math.max(2, Math.floor(tilePx * 0.1));
  ctx.strokeStyle = 'rgba(0,0,0,0.85)';
  ctx.strokeText(label, tx, ty);
  ctx.fillStyle = '#ffe9c4';
  ctx.fillText(label, tx, ty);
}
