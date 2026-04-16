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
}

export interface Renderer {
  mount(host: HTMLElement): void;
  resize(widthPx: number, heightPx: number): void;
  drawFrame(snap: FrameSnapshot): void;
  dispose(): void;
}
