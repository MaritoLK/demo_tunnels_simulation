// Wire shapes returned by the Flask API. Mirrors backend serializers.
// Keep this file the single source of truth for the over-the-wire contract —
// every other module importing Tile/Agent gets consistent types.

// --- Wire-mirrored constants -------------------------------------------
// Numeric constants whose canonical home is the backend; mirrored here so
// UI code (cargo bars, phase progress, etc.) doesn't pluck literals at
// every call site. If you change a backend value, update these too.

// Maximum cargo per agent at tier 0. Backend: backend/app/engine/needs.py
// CARRY_MAX. Per-tier values live in TIER_BENEFITS below.
export const CARRY_MAX = 8;

// Wood / stone cost to REACH each colony tier. Index 0 is the freebie
// founder tier. Mirrors backend `config.UPGRADE_TIER_COSTS` so the
// ColonyPanel can show "wood 12/15, stone 6/8 → tier 2" without an
// extra wire field. Keep both files in lockstep.
export const UPGRADE_TIER_COSTS = [
  { wood: 0,  stone: 0  },
  { wood: 15, stone: 8  },
  { wood: 40, stone: 25 },
] as const;
export const MAX_COLONY_TIER = UPGRADE_TIER_COSTS.length - 1;

// Tier benefits — mirrors backend `config.TIER_BENEFITS`. ColonyPanel
// shows the upcoming row so the demo viewer reads "what does the next
// upgrade get me?" at a glance. Keys match the backend table verbatim.
export interface TierBenefit {
  cargo_cap: number;
  pop_cap: number;
  move_cost_reduction: number;
  rest_energy: number;
  eat_cost: number;
}
export const TIER_BENEFITS: readonly TierBenefit[] = [
  { cargo_cap:  8, pop_cap:  8, move_cost_reduction: 0, rest_energy:  5, eat_cost: 6 },
  { cargo_cap: 12, pop_cap: 12, move_cost_reduction: 1, rest_energy:  8, eat_cost: 5 },
  { cargo_cap: 16, pop_cap: 16, move_cost_reduction: 2, rest_energy: 12, eat_cost: 4 },
];

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
  // Per-resource pouches. Total weight (cargo_food*1 + cargo_wood*2
  // + cargo_stone*3) is capped at CARRY_MAX. Drained at camp deposit.
  // Optional for legacy snapshots pre-multi-resource — the renderer
  // and tooltip treat undefined as 0.
  cargo_food?: number;
  cargo_wood?: number;
  cargo_stone?: number;
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
  // Wood / stone stockpiles — what camp-tier upgrades cost. Optional
  // for older snapshots during a rolling deploy; renderer treats
  // missing as 0.
  wood_stock?: number;
  stone_stock?: number;
  // Camp tier (0/1/2). Drives the house sprite swap and the per-agent
  // fog reveal radius bonus. Optional for back-compat — undefined
  // reads as 0.
  tier?: number;
  // Sprite-asset key — decouples agent sprite selection from colony.name
  // so a future colony rename doesn't lose its visual identity.
  // Wire values today: 'Red' | 'Blue' | 'Purple' | 'Yellow' (open union).
  sprite_palette: string;
  // Tiles this colony has revealed. Cumulative — never reset during a
  // run. Sorted on the wire so identical fog produces identical bytes —
  // keeps the nginx micro-cache and SSE diff happy. Optional because
  // older clients may receive a payload without it during a rolling
  // deploy; the renderer falls back to "all explored" when missing
  // rather than blacking out the world.
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
