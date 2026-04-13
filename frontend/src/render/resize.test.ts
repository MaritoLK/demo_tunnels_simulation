import { describe, it, expect, beforeEach, vi } from 'vitest';
import { Canvas2DRenderer } from './Canvas2DRenderer';

// The rAF loop in WorldCanvas calls renderer.resize(w, h) every frame
// (see WorldCanvas.tsx:160). Each canvas width/height reassignment
// clears the backing store and resets all 2D context state — not
// dangerous (we re-apply setTransform + imageSmoothingEnabled right
// after), but it's 60 wasted alloc/reset cycles per second when the
// dimensions haven't actually changed. Guarding with a cached
// (lastW, lastH) turns "resize every frame" into "resize only on
// real changes," which is what the WorldCanvas loop actually wants.
describe('Canvas2DRenderer.resize — idempotence', () => {
  let host: HTMLDivElement;

  beforeEach(() => {
    const ctxSpy = {
      save: vi.fn(), restore: vi.fn(),
      translate: vi.fn(), rotate: vi.fn(), scale: vi.fn(),
      setTransform: vi.fn(),
      fillRect: vi.fn(), fill: vi.fn(), stroke: vi.fn(),
      beginPath: vi.fn(), arc: vi.fn(), ellipse: vi.fn(),
      setLineDash: vi.fn(),
      fillStyle: '', strokeStyle: '', lineWidth: 0,
      imageSmoothingEnabled: false,
    };
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(
      () => ctxSpy as unknown as CanvasRenderingContext2D,
    );
    host = document.createElement('div');
    document.body.appendChild(host);
  });

  it('assigns canvas.width/height on first resize', () => {
    const r = new Canvas2DRenderer();
    r.mount(host);
    const canvas = host.querySelector('canvas')!;
    const widthSetSpy = vi.fn();
    const heightSetSpy = vi.fn();
    // Spy on the underlying setter so we can count assignments.
    Object.defineProperty(canvas, 'width', {
      set: widthSetSpy,
      get: () => 0,
      configurable: true,
    });
    Object.defineProperty(canvas, 'height', {
      set: heightSetSpy,
      get: () => 0,
      configurable: true,
    });
    r.resize(320, 200);
    expect(widthSetSpy).toHaveBeenCalledTimes(1);
    expect(heightSetSpy).toHaveBeenCalledTimes(1);
    r.dispose();
  });

  it('skips canvas.width/height assignment when called again with same dims', () => {
    const r = new Canvas2DRenderer();
    r.mount(host);
    const canvas = host.querySelector('canvas')!;

    // First resize happens with the default defined width/height
    // setters, so we install the spy AFTER it.
    r.resize(320, 200);

    const widthSetSpy = vi.fn();
    const heightSetSpy = vi.fn();
    Object.defineProperty(canvas, 'width', {
      set: widthSetSpy,
      get: () => 320,
      configurable: true,
    });
    Object.defineProperty(canvas, 'height', {
      set: heightSetSpy,
      get: () => 200,
      configurable: true,
    });

    // Call five more times with the same dims — simulating 5 rAF ticks
    // on an unchanged frame. No further assignments should happen.
    r.resize(320, 200);
    r.resize(320, 200);
    r.resize(320, 200);
    r.resize(320, 200);
    r.resize(320, 200);
    expect(widthSetSpy).not.toHaveBeenCalled();
    expect(heightSetSpy).not.toHaveBeenCalled();
    r.dispose();
  });

  it('re-assigns when dimensions change after a stable period', () => {
    const r = new Canvas2DRenderer();
    r.mount(host);
    const canvas = host.querySelector('canvas')!;

    r.resize(320, 200);
    r.resize(320, 200);

    const widthSetSpy = vi.fn();
    const heightSetSpy = vi.fn();
    Object.defineProperty(canvas, 'width', {
      set: widthSetSpy,
      get: () => 320,
      configurable: true,
    });
    Object.defineProperty(canvas, 'height', {
      set: heightSetSpy,
      get: () => 200,
      configurable: true,
    });

    r.resize(640, 400);
    expect(widthSetSpy).toHaveBeenCalledTimes(1);
    expect(heightSetSpy).toHaveBeenCalledTimes(1);
    r.dispose();
  });
});
