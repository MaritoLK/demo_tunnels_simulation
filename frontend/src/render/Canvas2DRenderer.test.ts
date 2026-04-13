import { describe, it, expect, beforeEach, vi } from 'vitest';
import { Canvas2DRenderer } from './Canvas2DRenderer';
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
  fill: ReturnType<typeof vi.fn>;
  stroke: ReturnType<typeof vi.fn>;
  beginPath: ReturnType<typeof vi.fn>;
  arc: ReturnType<typeof vi.fn>;
  ellipse: ReturnType<typeof vi.fn>;
  setLineDash: ReturnType<typeof vi.fn>;
  fillStyle: string;
  strokeStyle: string;
  lineWidth: number;
  imageSmoothingEnabled: boolean;
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
    fill: vi.fn(),
    stroke: vi.fn(),
    beginPath: vi.fn(),
    arc: vi.fn(),
    ellipse: vi.fn(),
    setLineDash: vi.fn(),
    fillStyle: '',
    strokeStyle: '',
    lineWidth: 0,
    imageSmoothingEnabled: false,
  };
}

function makeSnap(overrides: Partial<FrameSnapshot> = {}): FrameSnapshot {
  // 1x1 world with one selected agent on top of a grass tile.
  return {
    width: 1,
    height: 1,
    tiles: [[{ x: 0, y: 0, terrain: 'grass', resource_type: null, resource_amount: 0 }]],
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
      },
    ],
    tilePx: 32,
    cameraX: 0,
    cameraY: 0,
    selectedAgentId: 7,
    reducedMotion: false,
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
