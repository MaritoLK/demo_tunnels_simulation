// Wire shapes returned by the Flask API. Mirrors backend serializers.
// Keep this file the single source of truth for the over-the-wire contract —
// every other module importing Tile/Agent gets consistent types.

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
