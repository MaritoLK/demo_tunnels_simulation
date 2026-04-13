// Read the user's current `prefers-reduced-motion` preference.
//
// Defensive about non-browser environments: falls back to `false` when
// `window.matchMedia` is missing. The renderer uses this to branch
// away from animated decorations (rotating selection rings, breathing
// halos) when the OS asks for calmer UI.
//
// This is a point-in-time read. If the preference changes while the
// app is running (user toggles the OS setting), the next frame picks
// it up. No subscription needed — the rAF loop is already per-frame.
export function isReducedMotion(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return false;
  }
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}
