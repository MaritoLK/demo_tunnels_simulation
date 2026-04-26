// Per-agent lifecycle fade state.
//
// Why we need it:
//   Backend mutates agent lists. A new spawn pops into view; a death
//   + cleanup vanishes. Today both are instant: a full-opacity pawn
//   appears or disappears in one frame, which reads as "jump / glitch"
//   even at 60 fps. A 250 ms cubic fade bridges the cut.
//
// Model:
//   state: 'in' | 'alive' | 'out'
//   in:    alpha = easeOutCubic((now - startedAt) / FADE_MS), until ≥1
//   alive: alpha = 1
//   out:   alpha = 1 - easeOutCubic((now - startedAt) / FADE_MS), until ≤0
//          then pruned.

import { easeOutCubic } from './ease';

export const FADE_MS = 250;

type Entry = { state: 'in' | 'alive' | 'out'; startedAt: number };

export class LifecycleFade {
  private map = new Map<number, Entry>();

  has(id: number): boolean {
    return this.map.has(id);
  }

  update({ present, now }: { present: Set<number>; now: number }): void {
    // The two loops below operate on disjoint key sets by construction:
    // `present` (loop 1) and `!present.has(id)` (loop 2). Don't pass an id
    // in `present` that also needs fading out — there's no such state.
    // Transition in / confirm alive
    for (const id of present) {
      const e = this.map.get(id);
      if (!e) {
        this.map.set(id, { state: 'in', startedAt: now });
      } else if (e.state === 'in' && now - e.startedAt >= FADE_MS) {
        this.map.set(id, { state: 'alive', startedAt: now });
      } else if (e.state === 'out') {
        // Reappeared mid-fade-out. Continue from the current alpha by
        // switching to 'in' with a back-dated startedAt, so the next
        // frame's eased value matches the previous frame's. Inverting
        // easeOutCubic(t) = 1 − (1−t)³ at the current α gives the
        // fade-in offset: t = 1 − ∛(1 − α). Without this the alpha
        // would jump from the fade-out value straight to 1 — the
        // snap-glitch this module exists to prevent.
        const alpha = 1 - easeOutCubic((now - e.startedAt) / FADE_MS);
        const inProgress = 1 - Math.cbrt(1 - alpha);
        this.map.set(id, { state: 'in', startedAt: now - FADE_MS * inProgress });
      }
    }
    // Transition out / prune completed
    for (const [id, e] of this.map) {
      if (!present.has(id)) {
        if (e.state !== 'out') {
          this.map.set(id, { state: 'out', startedAt: now });
        } else if (now - e.startedAt > FADE_MS) {
          this.map.delete(id);
        }
      }
    }
  }

  alphaFor(id: number, now: number): number {
    const e = this.map.get(id);
    if (!e) return 0;
    const dt = now - e.startedAt;
    if (e.state === 'alive') return 1;
    // easeOutCubic clamps to [0, 1] internally, so we don't pre-clamp here.
    if (e.state === 'in') return easeOutCubic(dt / FADE_MS);
    // state === 'out'
    return 1 - easeOutCubic(dt / FADE_MS);
  }
}
