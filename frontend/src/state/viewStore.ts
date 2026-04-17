// Zustand store for UI / view state.
//
// What belongs here (not in React Query):
//   - Selection (which agent is picked in the panel).
//   - Camera (pan offset, zoom factor) — persists across refetches.
//   - Timeline scrub position for a future generational view.
//
// What does NOT belong here:
//   - Server state (world, agents, events). That's React Query's job.
//   - Anything derivable from server state.
//
// Zustand picked over Context/Redux because:
//   - No Provider pollution: any component just imports the hook.
//   - Sub-millisecond selectors via shallow compare — the canvas draws at
//     60fps and cannot afford re-render storms from naive Context.
//   - 1kB footprint; Redux is ~10× that and brings ceremony we don't need.
import { create } from 'zustand';

export interface ViewState {
  selectedAgentId: number | null;
  // Tile selection is mutually exclusive with agent selection: selecting
  // one clears the other. Canvas click hit-tests agents first, falls
  // back to tile if no agent hit.
  selectedTile: { x: number; y: number } | null;
  cameraX: number;
  cameraY: number;
  zoom: number; // tile-size multiplier; 1.0 = default TILE_PX

  selectAgent: (id: number | null) => void;
  selectTile: (tile: { x: number; y: number } | null) => void;
  pan: (dx: number, dy: number) => void;
  setCamera: (x: number, y: number) => void;
  setZoom: (z: number) => void;
  reset: () => void;
}

const INITIAL: Pick<ViewState, 'selectedAgentId' | 'selectedTile' | 'cameraX' | 'cameraY' | 'zoom'> = {
  selectedAgentId: null,
  selectedTile: null,
  cameraX: 0,
  cameraY: 0,
  zoom: 1.0,
};

export const useViewStore = create<ViewState>((set) => ({
  ...INITIAL,
  selectAgent: (id) => set({ selectedAgentId: id, selectedTile: null }),
  selectTile: (tile) => set({ selectedTile: tile, selectedAgentId: null }),
  pan: (dx, dy) => set((s) => ({ cameraX: s.cameraX + dx, cameraY: s.cameraY + dy })),
  setCamera: (x, y) => set({ cameraX: x, cameraY: y }),
  setZoom: (z) => set({ zoom: Math.max(0.0625, Math.min(4.0, z)) }),
  reset: () => set(INITIAL),
}));
