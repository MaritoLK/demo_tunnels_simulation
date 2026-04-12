// Wire shapes returned by the Flask API. Mirrors backend serializers.
// Keep this file the single source of truth for the over-the-wire contract —
// every other module importing Tile/Agent gets consistent types.

export type Terrain = 'grass' | 'water' | 'forest' | 'stone' | 'sand';
export type ResourceType = 'food' | 'wood' | 'stone' | null;

export interface Tile {
  x: number;
  y: number;
  terrain: Terrain;
  resource_type: ResourceType;
  resource_amount: number;
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
}

export interface SimulationSummary {
  tick: number;
  seed: number | null;
  width: number;
  height: number;
  agent_count: number;
  alive_count: number;
  running: boolean;
}

export interface EventRow {
  tick: number;
  agent_id: number | null;
  type: string; // wire-renamed from event_type on the backend
  description: string | null;
  data: unknown;
}
