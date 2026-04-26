// Client-side interpolation buffer.
//
// We keep the last 2 server-pushed snapshots. The canvas renders at
// `renderTime = serverTimeNow - INTERP_DELAY_MS`, which is intentionally
// in the past — this guarantees that for most of the time, renderTime
// falls BETWEEN two known snapshots, so we're always interpolating
// between measured truths instead of extrapolating past the last one.
//
// Per-agent output:
//   positions:     Map<id, {x, y, alphaRaw}> — raw lerp fraction in [0,1]
//   newlyPresent:  ids appearing in the newer snap but not the older
//   departed:      ids present in the older but not newer; drawn at last-known
//
// Why not 3+ snapshots: bandwidth and state are minimal at 1 Hz tick;
// a second's worth of memory is one full snapshot. Two is enough to
// bracket renderTime in steady state.

export interface AgentSample {
  id: number;
  x: number;
  y: number;
}

export interface Snap {
  serverTimeMs: number;
  tick: number;
  agents: AgentSample[];
}

export interface SampleResult {
  positions: Map<number, { x: number; y: number; alphaRaw: number }>;
  newlyPresent: number[];
  departed: number[];
  /** The newer snap's tick — monotonic with respect to push order. */
  tick: number;
}

const BUF_SIZE = 2;

export class InterpBuffer {
  private buf: Snap[] = [];

  push(s: Snap): void {
    this.buf.push(s);
    if (this.buf.length > BUF_SIZE) this.buf.shift();
  }

  sampleAt(renderTimeMs: number): SampleResult {
    if (this.buf.length === 0) {
      return { positions: new Map(), newlyPresent: [], departed: [], tick: -1 };
    }
    if (this.buf.length === 1) {
      // Buffer not yet warm (first snapshot only). Return the single
      // known truth fully opaque. alphaRaw: 1 is NOT a lerp progress
      // signal here — there's nothing to lerp between — it just means
      // "display as drawn." LifecycleFade still runs its own 250ms
      // fade-in on top because this is each id's first appearance.
      const only = this.buf[0];
      const positions = new Map<number, { x: number; y: number; alphaRaw: number }>();
      for (const a of only.agents) positions.set(a.id, { x: a.x, y: a.y, alphaRaw: 1 });
      return { positions, newlyPresent: [], departed: [], tick: only.tick };
    }
    const [older, newer] = this.buf;
    const span = newer.serverTimeMs - older.serverTimeMs;
    const raw = span > 0 ? (renderTimeMs - older.serverTimeMs) / span : 1;
    const t = Math.max(0, Math.min(1, raw));

    const olderById = new Map<number, AgentSample>();
    for (const a of older.agents) olderById.set(a.id, a);
    const newerById = new Map<number, AgentSample>();
    for (const a of newer.agents) newerById.set(a.id, a);

    const positions = new Map<number, { x: number; y: number; alphaRaw: number }>();
    const newlyPresent: number[] = [];
    const departed: number[] = [];

    for (const [id, nSamp] of newerById) {
      const o = olderById.get(id);
      if (o) {
        positions.set(id, {
          x: o.x + (nSamp.x - o.x) * t,
          y: o.y + (nSamp.y - o.y) * t,
          alphaRaw: t,
        });
      } else {
        newlyPresent.push(id);
        positions.set(id, { x: nSamp.x, y: nSamp.y, alphaRaw: 1 });
      }
    }
    for (const [id, o] of olderById) {
      if (!newerById.has(id)) {
        departed.push(id);
        // Pin at last-known; lifecycle fade handles the visual exit.
        positions.set(id, { x: o.x, y: o.y, alphaRaw: 1 });
      }
    }

    return { positions, newlyPresent, departed, tick: newer.tick };
  }

  /** Time gap between the two newest snapshots in the buffer, or null
   *  while the buffer hasn't accumulated two snapshots yet. The renderer
   *  uses this as an adaptive interp delay so its sample clock walks
   *  forward between snaps at 1 ms per ms — without it, sampling at a
   *  fixed offset from the latest server timestamp leaves the agent
   *  pinned at one interp fraction until the next snap pops them again. */
  lastSnapInterval(): number | null {
    if (this.buf.length < 2) return null;
    return this.buf[1].serverTimeMs - this.buf[0].serverTimeMs;
  }
}
