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


describe('Canvas2DRenderer — lifecycle fade applies to overlays', () => {
  // Regression: lifecycleFade alpha used to apply only to the body
  // sprite/disc. Halo, label, cargo pip, shadow stayed at full alpha
  // during fade-in/out, producing 250 ms of "ghost body with fully
  // opaque hovering halo + label" right after sim load — the visual
  // contradiction lifecycleFade was supposed to prevent.
  let host: HTMLDivElement;

  beforeEach(() => {
    host = document.createElement('div');
    document.body.appendChild(host);
  });

  function alphaCapturingSpy(): { spy: CtxSpy; alphaAt: Map<string, number[]> } {
    const spy = makeCtxSpy();
    const alphaAt = new Map<string, number[]>();
    // Real canvas save/restore preserves globalAlpha; the default vi.fn()
    // mocks do not. Without a state stack, an inner ctx.globalAlpha
    // assignment leaks past the matching restore() and pollutes the
    // outer wrap, so this test would lie about which alpha each draw
    // call actually saw.
    const stack: number[] = [];
    spy.save = vi.fn(() => { stack.push(spy.globalAlpha); });
    spy.restore = vi.fn(() => {
      const a = stack.pop();
      if (a !== undefined) spy.globalAlpha = a;
    });
    const record = (key: string) => {
      const arr = alphaAt.get(key) ?? [];
      arr.push(spy.globalAlpha);
      alphaAt.set(key, arr);
    };
    spy.fill = vi.fn(() => record('fill'));
    spy.stroke = vi.fn(() => record('stroke'));
    spy.fillText = vi.fn(() => record('fillText'));
    return { spy, alphaAt };
  }

  it('label, halo, cargo pip, and shadow share lifecycleAlpha with the body', () => {
    const { spy, alphaAt } = alphaCapturingSpy();
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(
      () => spy as unknown as CanvasRenderingContext2D,
    );
    const r = new Canvas2DRenderer();
    r.mount(host);
    r.resize(64, 64);
    r.drawFrame(makeSnap({
      // Big enough to render the label (LABEL_MIN_TILE_PX = 14).
      tilePx: 32,
      colonies: [
        { id: 1, name: 'Red', color: '#e74c3c', camp_x: 0, camp_y: 0, food_stock: 0, growing_count: 0, sprite_palette: 'Red' },
      ],
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
          state: 'foraging',
          alive: true,
          colony_id: 1,
          cargo_food: 4, cargo_wood: 0, cargo_stone: 0,
          decision_reason: '',
        },
      ],
      selectedAgentId: null,
    }));
    // First render = lifecycle fade-in just started, so alpha = 0. The
    // label, the colony halo, the cargo pip, and the shadow ellipse must
    // all draw at < 1 globalAlpha — proving they sit inside the same
    // lifecycle wrap as the body sprite/disc.
    const labelAlphas = alphaAt.get('fillText') ?? [];
    expect(labelAlphas.length).toBeGreaterThan(0);
    for (const a of labelAlphas) expect(a).toBeLessThan(1);

    const fills = alphaAt.get('fill') ?? [];
    // At least one overlay-class fill (shadow, cargo pip, gloss, halo)
    // had to land at < 1 alpha — pre-fix every one of these was 1.
    expect(fills.some((a) => a < 1)).toBe(true);

    r.dispose();
  });
});


describe('Canvas2DRenderer — interpolation across snapshots', () => {
  // Regression: sampleTime used to be anchored to snap.serverNowMs minus
  // a fixed offset. Server time only advances when a new snapshot
  // arrives, so the interp fraction was frozen between snaps — the
  // agent popped to a fixed position when each snap arrived and then
  // sat still until the next one (the "teleport every tick" feel).
  // Fix: anchor to performance.now() and adapt the offset to the
  // observed snap interval, so the sample clock walks 1 ms per ms and
  // the agent is animating every frame.
  let host: HTMLDivElement;
  let nowSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    host = document.createElement('div');
    document.body.appendChild(host);
  });

  afterEach(() => {
    nowSpy?.mockRestore();
  });

  it('agent body x advances smoothly between server snapshots', () => {
    let mockNow = 0;
    nowSpy = vi.spyOn(performance, 'now').mockImplementation(() => mockNow);

    // Capture shadow ellipse cx — line 1 is the body's drop shadow,
    // its cx is the first thing drawn per agent and reflects the
    // interpolated position before any other state churn.
    const ctxSpy = makeCtxSpy();
    const ellipseCx: number[] = [];
    ctxSpy.ellipse = vi.fn((cx: number) => { ellipseCx.push(cx); });
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(
      () => ctxSpy as unknown as CanvasRenderingContext2D,
    );

    const r = new Canvas2DRenderer();
    r.mount(host);
    r.resize(64, 64);

    // Two snaps 1000 ms apart (client time). Agent steps from x=0 to x=10.
    mockNow = 0;
    r.ingestSnapshot({ serverTimeMs: 1, tick: 1, agents: [{ id: 7, x: 0, y: 0 }] });
    mockNow = 1000;
    r.ingestSnapshot({ serverTimeMs: 2, tick: 2, agents: [{ id: 7, x: 10, y: 0 }] });

    function bodyAgent(x: number) {
      return [
        { id: 7, name: 'A', x, y: 0, health: 100, hunger: 80, energy: 80,
          social: 80, age: 0, state: 'idle', alive: true, colony_id: null,
          decision_reason: '' },
      ];
    }

    // Draw at three increasing client times. Ellipse cx must climb
    // monotonically — equal cx across frames would be the teleport bug.
    mockNow = 1100;
    ellipseCx.length = 0;
    r.drawFrame(makeSnap({ tilePx: 32, agents: bodyAgent(10), selectedAgentId: null }));
    const cxAt1100 = ellipseCx[0];

    mockNow = 1500;
    ellipseCx.length = 0;
    r.drawFrame(makeSnap({ tilePx: 32, agents: bodyAgent(10), selectedAgentId: null }));
    const cxAt1500 = ellipseCx[0];

    mockNow = 1900;
    ellipseCx.length = 0;
    r.drawFrame(makeSnap({ tilePx: 32, agents: bodyAgent(10), selectedAgentId: null }));
    const cxAt1900 = ellipseCx[0];

    expect(cxAt1500).toBeGreaterThan(cxAt1100);
    expect(cxAt1900).toBeGreaterThan(cxAt1500);

    r.dispose();
  });
});


describe('pickVariant', () => {
  const baseAgent = { state: 'exploring', x: 1, y: 1, cargo_food: 0, cargo_wood: 0, cargo_stone: 0 };

  it('returns idle when stationary with no cargo', () => {
    expect(pickVariant(baseAgent, { x: 1, y: 1 })).toBe('idle');
  });

  it('returns idleMeat when stationary with cargo', () => {
    expect(pickVariant({ ...baseAgent, cargo_food: 2 }, { x: 1, y: 1 })).toBe('idleMeat');
  });

  it('returns run when moving, no cargo', () => {
    expect(pickVariant(baseAgent, { x: 0, y: 1 })).toBe('run');
  });

  it('returns runMeat when moving with cargo', () => {
    expect(pickVariant({ ...baseAgent, cargo_wood: 3 }, { x: 0, y: 1 })).toBe('runMeat');
  });

  it('returns idle when prev is undefined (first frame)', () => {
    expect(pickVariant(baseAgent, undefined)).toBe('idle');
  });
});
