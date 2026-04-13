// Pure state transition for the HUD tick-pulse animation.
//
// Why a function, not inline in useEffect: the inlined version had a
// latent bug where the "previous tick" ref only advanced on the
// no-pulse branch, because the pulse branch early-returned with a
// setTimeout cleanup. The ref was frozen at the first observed value;
// the pulse fired by accident because new ticks are always != 0.
// Extracting the transition forces the invariant: prev ALWAYS advances
// to curr, regardless of whether we pulsed.
export function nextTickPulseState(
  prev: number | null,
  curr: number | null,
): { pulse: boolean; next: number | null } {
  const pulse = prev !== null && curr !== null && prev !== curr;
  return { pulse, next: curr };
}
