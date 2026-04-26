// Render adapter interface.
//
// The component layer never touches <canvas> APIs directly — it calls
// a Renderer. Today the only impl is Canvas2DRenderer. Tomorrow, when
// the sim grows past ~5k moving agents and Canvas2D GC-pressures, the
// swap to a PixiJS / WebGL-batched renderer is this interface plus a
// new file — no component changes.
//
// Invariants:
//   - mount() is called once with a host element; the renderer owns
//     the <canvas> inside it and all its GL/2D state.
//   - resize() is called when the viewport or world dimensions change.
//   - drawFrame() is called once per animation frame with an immutable
//     snapshot; the renderer does not mutate it and does not cache
//     references to it past the call.
//   - dispose() tears down any owned resources (event listeners, GL
//     contexts, RAF handles).
import type { Agent, Colony, Tile } from '../api/types';

export interface FrameSnapshot {
  width: number; // world width in tiles
  height: number; // world height in tiles
  tiles: Tile[][]; // tiles[y][x]
  agents: Agent[];
  colonies: Colony[];
  // Camera + UI state, resolved at frame-prep time so the renderer
  // is a pure function of snapshot → pixels.
  tilePx: number; // effective tile size in CSS pixels (zoom applied)
  cameraX: number;
  cameraY: number;
  selectedAgentId: number | null;
  // Selected tile (mutually exclusive with selectedAgentId). The
  // renderer draws a diamond outline on this tile — subtler than the
  // agent selection ring so a selected tile doesn't shout over pawns
  // standing on it.
  selectedTile: { x: number; y: number } | null;
  // When true, the renderer must skip animated decoration (rotating
  // rings, pulsing halos, etc.) and draw a static equivalent. Sourced
  // from `prefers-reduced-motion: reduce` and threaded through the
  // snapshot rather than read inside the renderer, so the renderer
  // stays a pure function of snapshot + clock.
  reducedMotion: boolean;
  // Backend tick counter. The renderer uses tick-advance as the
  // signal to snapshot previous positions for inter-poll
  // interpolation. Scalar render input — not a simulation concern
  // leaking in, same category as tilePx.
  currentTick: number;
  // Current day/night phase from the simulation. Used to tint
  // state icon overlays (reduced opacity at night). May be missing
  // during early load — falls back to 'day'.
  phase?: string;
  // Server wall-clock at snapshot time (ms since epoch). Passed
  // through to the renderer so InterpBuffer can convert server time
  // to a render time (server_time_ms - INTERP_DELAY_MS). Optional
  // so legacy fixtures and tests that omit it still type-check.
  serverNowMs?: number;
  // Per-agent latest d20 forage roll + the wall-clock instant the
  // event arrived. The renderer flashes a "1d20 = N" chip above the
  // agent for a short window after each roll. Optional so tests and
  // older payloads without dice events still type-check; map values
  // older than the chip duration are simply ignored at render time.
  recentForageRolls?: Map<number, { roll: number; receivedAtMs: number }>;
}

export interface Renderer {
  mount(host: HTMLElement): void;
  resize(widthPx: number, heightPx: number): void;
  drawFrame(snap: FrameSnapshot): void;
  dispose(): void;
  /** Push a new server snapshot into the interpolation buffer.
   *  Optional — adapters that do not implement interpolation may omit this. */
  ingestSnapshot?(snap: { serverTimeMs: number; tick: number; agents: Array<{ id: number; x: number; y: number }> }): void;
}
