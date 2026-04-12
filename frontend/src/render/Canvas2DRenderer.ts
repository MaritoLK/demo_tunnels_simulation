// Canvas2D implementation of Renderer.
//
// Scope/sizing: comfortably handles 100×100 tiles and ~100 moving agents
// at 60fps on modest hardware. Past that, the fillRect-per-tile cost
// dominates; the swap point is roughly "when the Chrome profiler shows
// >4ms in paint per frame" — at that point replace this file with a
// PixiJS adapter that uses sprite batching.
//
// Choices:
//   - Device-pixel-ratio scaling: set canvas.width to logical × DPR,
//     then ctx.scale(DPR, DPR). Otherwise every pixel is blurred on
//     retina displays. Common forgotten step, interview-quotable.
//   - imageSmoothingEnabled = false: we want crisp tile grid, not
//     bilinear interpolation between colours.
//   - Agents drawn last so they sit above terrain.
//   - Selected agent gets a ring, not a colour swap — colour carries
//     meaning (health), shouldn't be overloaded with selection.
import type { Renderer, FrameSnapshot } from './Renderer';
import type { Terrain } from '../api/types';

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
  }

  resize(widthPx: number, heightPx: number): void {
    if (!this.canvas || !this.ctx) return;
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
    const { width, height, tiles, agents, tilePx, cameraX, cameraY, selectedAgentId } = snap;

    ctx.save();
    // Background clear — match the shell ground so the canvas feels
    // continuous with the page when the world is smaller than the frame.
    ctx.fillStyle = '#0e1220';
    ctx.fillRect(0, 0, this.canvas.width / this.dpr, this.canvas.height / this.dpr);

    ctx.translate(cameraX, cameraY);

    // Terrain pass — flat biome fill, then a small darker speckle inset
    // to break up tile flatness. Deterministic by (x,y) so it doesn't
    // shimmer between frames. Cheap: one extra rect per tile.
    for (let y = 0; y < height; y++) {
      const row = tiles[y];
      if (!row) continue;
      for (let x = 0; x < width; x++) {
        const tile = row[x];
        if (!tile) continue;
        const px = x * tilePx;
        const py = y * tilePx;
        ctx.fillStyle = TERRAIN_FILL[tile.terrain] ?? '#000';
        ctx.fillRect(px, py, tilePx, tilePx);

        // Speckle placement: hash (x,y) into 4 corner positions so
        // neighbouring tiles look different without noise.
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
          ctx.fillStyle = RESOURCE_DOT_COLOUR[tile.resource_type] ?? '#fff';
          const cx = px + tilePx / 2;
          const cy = py + tilePx / 2;
          const r = Math.max(1.5, tilePx * 0.2);
          ctx.beginPath();
          ctx.arc(cx, cy, r, 0, Math.PI * 2);
          ctx.fill();
          // Tiny highlight for that game-y "item pickup" feel.
          ctx.fillStyle = 'rgba(255,255,255,0.45)';
          ctx.beginPath();
          ctx.arc(cx - r * 0.3, cy - r * 0.3, r * 0.35, 0, Math.PI * 2);
          ctx.fill();
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

      // Body.
      ctx.fillStyle = a.alive ? healthColour(a.health) : '#3a3f55';
      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, Math.PI * 2);
      ctx.fill();

      // Outline.
      ctx.strokeStyle = 'rgba(0,0,0,0.45)';
      ctx.lineWidth = Math.max(1, tilePx * 0.08);
      ctx.stroke();

      // Highlight for gloss.
      ctx.fillStyle = 'rgba(255,255,255,0.35)';
      ctx.beginPath();
      ctx.arc(cx - r * 0.3, cy - r * 0.35, r * 0.35, 0, Math.PI * 2);
      ctx.fill();

      if (a.id === selectedAgentId) {
        // Selection reads as UI, not data — two concentric dashed rings
        // rotating in opposite directions + a soft breathing halo. The
        // inner ring matches the body radius; the outer sits further
        // out so you can see the agent's own health colour through the
        // gap. `performance.now()` keys the animation; the renderer
        // stays a pure function of (snapshot, clock).
        const t = performance.now() / 1000;
        const ringGap = Math.max(2, tilePx * 0.22);

        // Breathing halo — soft coral bloom pulsing with `sigil-pulse`
        // timing so the empty-state sigil and selection ring feel like
        // the same visual language.
        const pulse = 0.5 + 0.5 * Math.sin(t * 2.2);
        ctx.fillStyle = `rgba(255, 123, 59, ${0.08 + pulse * 0.12})`;
        ctx.beginPath();
        ctx.arc(cx, cy, r + ringGap + 4 + pulse * 3, 0, Math.PI * 2);
        ctx.fill();

        ctx.strokeStyle = '#ff7b3b';
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

    ctx.restore();
  }

  dispose(): void {
    if (this.canvas && this.host) this.host.removeChild(this.canvas);
    this.canvas = null;
    this.ctx = null;
    this.host = null;
  }
}

function healthColour(health: number): string {
  // Map 0..100 → red..green. Simple HSL interpolation.
  const h = Math.max(0, Math.min(120, (health / 100) * 120));
  return `hsl(${h}, 70%, 55%)`;
}
