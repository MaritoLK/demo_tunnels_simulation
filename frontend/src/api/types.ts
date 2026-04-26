// Wire shapes returned by the Flask API. Mirrors backend serializers.
// Keep this file the single source of truth for the over-the-wire contract —
// every other module importing Tile/Agent gets consistent types.

// --- Wire-mirrored constants -------------------------------------------
// Numeric constants whose canonical home is the backend; mirrored here so
// UI code (cargo bars, phase progress, etc.) doesn't pluck literals at
// every call site. If you change a backend value, update these too.

// Maximum cargo per agent. Backend: backend/app/engine/needs.py CARRY_MAX.
export const CARRY_MAX = 8;

// Ticks per day/night phase. Backend: backend/app/engine/cycle.py TICKS_PER_PHASE.
export const TICKS_PER_PHASE = 30;

export type Terrain = 'grass' | 'water' | 'forest' | 'stone' | 'sand';
export type ResourceType = 'food' | 'wood' | 'stone' | null;
export type CropState = 'none' | 'growing' | 'mature';
export type Phase = 'dawn' | 'day' | 'dusk' | 'night';

export interface Tile {
  x: number;
  y: number;
  terrain: Terrain;
  resource_type: ResourceType;
  resource_amount: number;
  crop_state: CropState;
  crop_growth_ticks: number;
  crop_colony_id: number | null;
  // Static hazard. When TRUE the tile bites any agent that steps onto
  // it for WOLF_BITE damage. Persisted at world-generation, never
  // mutates during a run. Renderer hides the marker behind fog so the
  // player only sees wolves they've discovered.
  wolves?: boolean;
}

export interface WorldSnapshot {
  width: number;
  height: number;
  tiles: Tile[][]; // tiles[y][x]
}

export interface Agent {
  id: number;
  name: string;
  x: number;
  y: number;
  state: string;
  hunger: number;
  energy: number;
  social: number;
  health: number;
  age: number;
  alive: boolean;
  colony_id: number | null;
  // True once the agent's social need hit zero. One-way. Rogue agents
  // skip camp-seeking behaviour backend-side; the UI signals this
  // visually (dimmed halo, "rogue" badge in the panel). Optional on
  // the wire so legacy fixtures and older snapshots (pre-feat) keep
  // type-checking — undefined is treated as false everywhere we read it.
  rogue?: boolean;
  // Loner: flagged at spawn for 2 agents per sim (when count > 4).
  // Their social need decays ~4× faster, making them the most likely
  // candidates to tip into rogue within a demo window.
  loner?: boolean;
  // Units of food in the agent's pouch (0..CARRY_MAX). Drained by
  // deposit at camp. Optional for legacy snapshots pre-cargo.
  cargo?: number;
  // Engine's own one-line explanation of the last decide_action branch
  // that fired for this agent. Empty string before the first tick.
  decision_reason: string;
}

export interface Colony {
  id: number;
  name: string;
  color: string; // '#rrggbb'
  camp_x: number;
  camp_y: number;
  food_stock: number;
  growing_count: number;
  // Sprite-asset key — decouples agent sprite selection from colony.name
  // so a future colony rename doesn't lose its visual identity.
  // Wire values today: 'Red' | 'Blue' | 'Purple' | 'Yellow' (open union).
  sprite_palette: string;
  // Tiles this colony has revealed since the last fog reset (cleared at
  // dusk → night). Sorted on the wire so identical fog produces
  // identical bytes — keeps the nginx micro-cache and SSE diff happy.
  // Optional because older clients may receive a payload without it
  // during a rolling deploy; the renderer falls back to "all explored"
  // when missing rather than blacking out the world.
  explored?: Array<[number, number]>;
}

export interface SimulationSummary {
  tick: number;
  seed: number | null;
  width: number;
  height: number;
  agent_count: number;
  alive_count: number;
  running: boolean;
  speed: number;
  day: number;
  phase: Phase;
  server_time_ms: number;
  tick_ms: number;
}

// Composite polling response — one round-trip replaces the four separate
// queries (sim/world/agents/events). See backend §9.27 for why.
export interface WorldStateResponse {
  sim: SimulationSummary;
  world: WorldSnapshot;
  agents: Agent[];
  colonies: Colony[];
  events: EventRow[];
}

export interface SimControlUpdate {
  running?: boolean;
  speed?: number;
}

export interface EventRow {
  tick: number;
  agent_id: number | null;
  type: string; // wire-renamed from event_type on the backend
  description: string | null;
  data: unknown;
}
