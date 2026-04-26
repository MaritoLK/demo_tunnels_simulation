// Ease-out cubic: y = 1 - (1 - t)^3.
// At t=0.5, y ≈ 0.875 — the body has already covered most of its
// travel early in the tick window, producing an arrival-biased motion
// that reads as biological instead of mechanical.
export function easeOutCubic(t: number): number {
  if (t <= 0) return 0;
  if (t >= 1) return 1;
  const inv = 1 - t;
  return 1 - inv * inv * inv;
}
