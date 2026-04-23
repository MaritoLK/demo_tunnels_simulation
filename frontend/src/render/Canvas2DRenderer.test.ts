import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Canvas2DRenderer, pickVariant } from './Canvas2DRenderer';
import type { FrameSnapshot } from './Renderer';

// Integration test: the renderer owns canvas 2D calls. We stub
// getContext to return a spy object and assert the right primitive
// calls were made.
//
// The specific property under test: when snap.reducedMotion is true,
// the selection ring path must not rotate (no spinning rings) and
// must not draw the breathing-halo pulse. A single static ring is
// acceptable. STUDY_NOTES §9.26 promised "all motion respects
// prefers-reduced-motion"; the canvas selection ring quietly broke
// that promise because it read `performance.now()` unconditionally.
//
// Why spy on the context: asserting rendered pixels in jsdom is not
// feasible. The interface we actually care about — "does the renderer
// ever call ctx.rotate when reducedMotion is true?" — is directly
// visible in the call log.

type CtxSpy = {
  save: ReturnType<typeof vi.fn>;
  restore: ReturnType<typeof vi.fn>;
  translate: ReturnType<typeof vi.fn>;
  rotate: ReturnType<typeof vi.fn>;
  scale: ReturnType<typeof vi.fn>;
  setTransform: ReturnType<typeof vi.fn>;
  fillRect: ReturnType<typeof vi.fn>;
  strokeRect: ReturnType<typeof vi.fn>;
  fill: ReturnType<typeof vi.fn>;
  stroke: ReturnType<typeof vi.fn>;
  beginPath: ReturnType<typeof vi.fn>;
  arc: ReturnType<typeof vi.fn>;
  ellipse: ReturnType<typeof vi.fn>;
  setLineDash: ReturnType<typeof vi.fn>;
  strokeText: ReturnType<typeof vi.fn>;
  fillText: ReturnType<typeof vi.fn>;
  fillStyle: string;
  strokeStyle: string;
  lineWidth: number;
  globalAlpha: number;
  imageSmoothingEnabled: boolean;
  font: string;
  textAlign: string;
  textBaseline: string;
};

function makeCtxSpy(): CtxSpy {
  return {
    save: vi.fn(),
    restore: vi.fn(),
    translate: vi.fn(),
    rotate: vi.fn(),
    scale: vi.fn(),
    setTransform: vi.fn(),
    fillRect: vi.fn(),
    strokeRect: vi.fn(),
    fill: vi.fn(),
    stroke: vi.fn(),
    beginPath: vi.fn(),
    arc: vi.fn(),
    ellipse: vi.fn(),
    setLineDash: vi.fn(),
    strokeText: vi.fn(),
    fillText: vi.fn(),
    fillStyle: '',
    strokeStyle: '',
    lineWidth: 0,
    globalAlpha: 1,
    imageSmoothingEnabled: false,
    font: '',
    textAlign: '',
    textBaseline: '',
  };
}

function makeSnap(overrides: Partial<FrameSnapshot> = {}): FrameSnapshot {
  // 1x1 world with one selected agent on top of a grass tile.
  return {
    width: 1,
    height: 1,
    tiles: [[{
      x: 0, y: 0, terrain: 'grass', resource_type: null, resource_amount: 0,
      crop_state: 'none', crop_growth_ticks: 0, crop_colony_id: null,
    }]],
    agents: [
      {
        id: 7,
        name: 'Test-Agent',
        x: 0,
        y: 0,
        health: 100,
        hunger: 80,
        energy: 80,
        social: 80,
        age: 0,
        state: 'idle',
        alive: true,
        colony_id: null,
        decision_reason: '',
      },
    ],
    colonies: [],
    tilePx: 32,
    cameraX: 0,
    cameraY: 0,
    selectedAgentId: 7,
    selectedTile: null,
    reducedMotion: false,
    currentTick: 0,
    ...overrides,
  };
}

describe('Canvas2DRenderer — reduced motion', () => {
  let ctxSpy: CtxSpy;
  let host: HTMLDivElement;

  beforeEach(() => {
    ctxSpy = makeCtxSpy();
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(
      () => ctxSpy as unknown as CanvasRenderingContext2D,
    );
    host = document.createElement('div');
    document.body.appendChild(host);
  });

  it('does NOT rotate the selection ring when reducedMotion is true', () => {
    const r = new Canvas2DRenderer();
    r.mount(host);
    r.resize(32, 32);
    r.drawFrame(makeSnap({ reducedMotion: true }));
    expect(ctxSpy.rotate).not.toHaveBeenCalled();
    r.dispose();
  });

  it('rotates the selection ring when reducedMotion is false (default motion)', () => {
    const r = new Canvas2DRenderer();
    r.mount(host);
    r.resize(32, 32);
    r.drawFrame(makeSnap({ reducedMotion: false }));
    // Two concentric rings rotate in opposite directions → at least 2 rotate calls.
    expect(ctxSpy.rotate).toHaveBeenCalled();
    expect(ctxSpy.rotate.mock.calls.length).toBeGreaterThanOrEqual(2);
    r.dispose();
  });

  it('still draws a selection ring when reducedMotion is true (not silent)', () => {
    // Reduced-motion must not mean "no selection indicator" — the user
    // still needs to see which agent is picked. Regression guard: the
    // static ring path must still call `arc` + `stroke` for the body
    // outline AND the selection ring.
    const r = new Canvas2DRenderer();
    r.mount(host);
    r.resize(32, 32);
    r.drawFrame(makeSnap({ reducedMotion: true }));
    // At minimum: body arc + body outline stroke + selection ring arc + ring stroke.
    expect(ctxSpy.stroke.mock.calls.length).toBeGreaterThanOrEqual(2);
    r.dispose();
  });
});

describe('Canvas2DRenderer — colony decorations', () => {
  let ctxSpy: CtxSpy;
  let host: HTMLDivElement;

  beforeEach(() => {
    ctxSpy = makeCtxSpy();
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(
      () => ctxSpy as unknown as CanvasRenderingContext2D,
    );
    host = document.createElement('div');
    document.body.appendChild(host);
  });

  it('draws a camp square for each colony (fillRect + strokeRect)', () => {
    // Camps are inset squares: one fillRect + one strokeRect per colony.
    // With the 1x1 default world the only fillRect the renderer emits
    // (in the procedural fallback path) is the background clear + camp,
    // so strokeRect is the cleaner signal.
    const r = new Canvas2DRenderer();
    r.mount(host);
    r.resize(32, 32);
    r.drawFrame(makeSnap({
      colonies: [
        { id: 1, name: 'Red', color: '#e74c3c', camp_x: 0, camp_y: 0, food_stock: 0, growing_count: 0, sprite_palette: 'Red' },
      ],
    }));
    expect(ctxSpy.strokeRect).toHaveBeenCalledTimes(1);
    r.dispose();
  });

  it('does not draw camp markers when colonies list is empty', () => {
    const r = new Canvas2DRenderer();
    r.mount(host);
    r.resize(32, 32);
    r.drawFrame(makeSnap());
    expect(ctxSpy.strokeRect).not.toHaveBeenCalled();
    r.dispose();
  });
});

describe('Canvas2DRenderer — tick interpolation', () => {
  // Renderer owns the prev→curr interpolation state; FrameSnapshot
  // only carries current integer positions + the scalar currentTick
  // that tells the renderer when to rotate its history. These tests
  // inspect the first `arc` call per frame — in the procedural
  // fallback path (no sprite atlas loaded, as in jsdom) that's the
  // agent body. Selection rings + gloss highlight come later in the
  // call log, so `mock.calls[0]` is the body position.
  let ctxSpy: CtxSpy;
  let host: HTMLDivElement;
  let nowSpy: ReturnType<typeof vi.spyOn>;
  let now: number;

  beforeEach(() => {
    ctxSpy = makeCtxSpy();
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(
      () => ctxSpy as unknown as CanvasRenderingContext2D,
    );
    host = document.createElement('div');
    document.body.appendChild(host);
    now = 0;
    nowSpy = vi.spyOn(performance, 'now').mockImplementation(() => now);
  });

  afterEach(() => {
    nowSpy.mockRestore();
  });

  function agentAt(id: number, x: number, y: number) {
    return {
      id, name: 'A', x, y, health: 100, hunger: 80, energy: 80, social: 80,
      age: 0, state: 'idle', alive: true, colony_id: null, decision_reason: '',
    };
  }

  function bodyXFromFirstArc(spy: CtxSpy, tilePx: number): number {
    const call = spy.arc.mock.calls[0];
    // arc(cx, cy, r, 0, 2π). Body centre is tilePx*bodyX + tilePx/2.
    const cx = call[0] as number;
    return (cx - tilePx / 2) / tilePx;
  }

  it('lerps the agent body between prev and curr over the poll window', () => {
    const r = new Canvas2DRenderer();
    r.mount(host);
    r.resize(64, 32);
    // Frame 1 at tick 0 establishes lastSeenPositions = (0,0).
    now = 0;
    r.drawFrame(makeSnap({
      width: 2, height: 1,
      tiles: [[
        { x: 0, y: 0, terrain: 'grass', resource_type: null, resource_amount: 0, crop_state: 'none', crop_growth_ticks: 0, crop_colony_id: null },
        { x: 1, y: 0, terrain: 'grass', resource_type: null, resource_amount: 0, crop_state: 'none', crop_growth_ticks: 0, crop_colony_id: null },
      ]],
      agents: [agentAt(7, 0, 0)],
      selectedAgentId: null, // drop selection so the first arc is definitively the body
      currentTick: 0,
    }));
    // Frame 2: tick advances, agent jumps 1 tile. alpha=0 → body still
    // at (0,0). One full pollIntervalMs (500ms) between frames 1 and 2
    // so the EMA sees a realistic delta and stays near its seed.
    ctxSpy.arc.mockClear();
    now = 500;
    r.drawFrame(makeSnap({
      width: 2, height: 1,
      tiles: [[
        { x: 0, y: 0, terrain: 'grass', resource_type: null, resource_amount: 0, crop_state: 'none', crop_growth_ticks: 0, crop_colony_id: null },
        { x: 1, y: 0, terrain: 'grass', resource_type: null, resource_amount: 0, crop_state: 'none', crop_growth_ticks: 0, crop_colony_id: null },
      ]],
      agents: [agentAt(7, 1, 0)],
      selectedAgentId: null,
      currentTick: 1,
    }));
    expect(bodyXFromFirstArc(ctxSpy, 32)).toBeCloseTo(0, 2);

    // Frame 3: half the poll window in — alpha≈0.5, body at ~0.5.
    ctxSpy.arc.mockClear();
    now = 500 + 250; // pollIntervalMs settled at 500
    r.drawFrame(makeSnap({
      width: 2, height: 1,
      tiles: [[
        { x: 0, y: 0, terrain: 'grass', resource_type: null, resource_amount: 0, crop_state: 'none', crop_growth_ticks: 0, crop_colony_id: null },
        { x: 1, y: 0, terrain: 'grass', resource_type: null, resource_amount: 0, crop_state: 'none', crop_growth_ticks: 0, crop_colony_id: null },
      ]],
      agents: [agentAt(7, 1, 0)],
      selectedAgentId: null,
      currentTick: 1,
    }));
    expect(bodyXFromFirstArc(ctxSpy, 32)).toBeCloseTo(0.5, 1);

    r.dispose();
  });

  it('snaps to target when reducedMotion is true', () => {
    const r = new Canvas2DRenderer();
    r.mount(host);
    r.resize(64, 32);
    now = 0;
    r.drawFrame(makeSnap({
      width: 2, height: 1,
      tiles: [[
        { x: 0, y: 0, terrain: 'grass', resource_type: null, resource_amount: 0, crop_state: 'none', crop_growth_ticks: 0, crop_colony_id: null },
        { x: 1, y: 0, terrain: 'grass', resource_type: null, resource_amount: 0, crop_state: 'none', crop_growth_ticks: 0, crop_colony_id: null },
      ]],
      agents: [agentAt(7, 0, 0)],
      selectedAgentId: null,
      currentTick: 0,
      reducedMotion: true,
    }));
    ctxSpy.arc.mockClear();
    now = 10;
    r.drawFrame(makeSnap({
      width: 2, height: 1,
      tiles: [[
        { x: 0, y: 0, terrain: 'grass', resource_type: null, resource_amount: 0, crop_state: 'none', crop_growth_ticks: 0, crop_colony_id: null },
        { x: 1, y: 0, terrain: 'grass', resource_type: null, resource_amount: 0, crop_state: 'none', crop_growth_ticks: 0, crop_colony_id: null },
      ]],
      agents: [agentAt(7, 1, 0)],
      selectedAgentId: null,
      currentTick: 1,
      reducedMotion: true,
    }));
    // reducedMotion = no lerp even at alpha=0 → body draws at target (x=1).
    expect(bodyXFromFirstArc(ctxSpy, 32)).toBeCloseTo(1, 2);
    r.dispose();
  });

  it('snaps when the agent moves more than one tile in a tick (no wall phasing)', () => {
    const r = new Canvas2DRenderer();
    r.mount(host);
    r.resize(320, 32);
    now = 0;
    r.drawFrame(makeSnap({
      width: 10, height: 1,
      tiles: [Array.from({ length: 10 }, (_, i) => ({
        x: i, y: 0, terrain: 'grass' as const, resource_type: null, resource_amount: 0,
        crop_state: 'none' as const, crop_growth_ticks: 0, crop_colony_id: null,
      }))],
      agents: [agentAt(7, 0, 0)],
      selectedAgentId: null,
      currentTick: 0,
    }));
    ctxSpy.arc.mockClear();
    now = 10;
    r.drawFrame(makeSnap({
      width: 10, height: 1,
      tiles: [Array.from({ length: 10 }, (_, i) => ({
        x: i, y: 0, terrain: 'grass' as const, resource_type: null, resource_amount: 0,
        crop_state: 'none' as const, crop_growth_ticks: 0, crop_colony_id: null,
      }))],
      agents: [agentAt(7, 5, 0)], // jumped 5 tiles — teleport, not a walk
      selectedAgentId: null,
      currentTick: 1,
    }));
    // Distance² = 25 > 2 → snap. Body at target (x=5), not lerped through 1..4.
    expect(bodyXFromFirstArc(ctxSpy, 32)).toBeCloseTo(5, 2);
    r.dispose();
  });

  it('new agents get prev=curr (no visible jump from origin)', () => {
    const r = new Canvas2DRenderer();
    r.mount(host);
    r.resize(64, 32);
    // Frame 1 — no agents yet.
    now = 0;
    r.drawFrame(makeSnap({
      width: 2, height: 1,
      tiles: [[
        { x: 0, y: 0, terrain: 'grass', resource_type: null, resource_amount: 0, crop_state: 'none', crop_growth_ticks: 0, crop_colony_id: null },
        { x: 1, y: 0, terrain: 'grass', resource_type: null, resource_amount: 0, crop_state: 'none', crop_growth_ticks: 0, crop_colony_id: null },
      ]],
      agents: [],
      selectedAgentId: null,
      currentTick: 0,
    }));
    ctxSpy.arc.mockClear();
    // Frame 2 — tick advanced, new agent appears at (1, 0). No prev entry,
    // so body draws at target instead of lerping from (0, 0) or stale data.
    now = 10;
    r.drawFrame(makeSnap({
      width: 2, height: 1,
      tiles: [[
        { x: 0, y: 0, terrain: 'grass', resource_type: null, resource_amount: 0, crop_state: 'none', crop_growth_ticks: 0, crop_colony_id: null },
        { x: 1, y: 0, terrain: 'grass', resource_type: null, resource_amount: 0, crop_state: 'none', crop_growth_ticks: 0, crop_colony_id: null },
      ]],
      agents: [agentAt(7, 1, 0)],
      selectedAgentId: null,
      currentTick: 1,
    }));
    expect(bodyXFromFirstArc(ctxSpy, 32)).toBeCloseTo(1, 2);
    r.dispose();
  });
});

describe('pickVariant', () => {
  const baseAgent = { state: 'exploring', x: 1, y: 1, cargo: 0 };

  it('returns idle when stationary with no cargo', () => {
    expect(pickVariant(baseAgent, { x: 1, y: 1 })).toBe('idle');
  });

  it('returns idleMeat when stationary with cargo', () => {
    expect(pickVariant({ ...baseAgent, cargo: 2 }, { x: 1, y: 1 })).toBe('idleMeat');
  });

  it('returns run when moving, no cargo', () => {
    expect(pickVariant(baseAgent, { x: 0, y: 1 })).toBe('run');
  });

  it('returns runMeat when moving with cargo', () => {
    expect(pickVariant({ ...baseAgent, cargo: 3 }, { x: 0, y: 1 })).toBe('runMeat');
  });

  it('returns idle when prev is undefined (first frame)', () => {
    expect(pickVariant(baseAgent, undefined)).toBe('idle');
  });
});
