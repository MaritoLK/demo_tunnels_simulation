// Scrollable feed of recent sim events.
//
// Two modes:
//   - Global: piggy-backs on the composite /world/state poll — zero
//     extra network traffic.
//   - Per-agent: separate filtered query that polls while the sim is
//     running. React Query's per-key cache keeps mode toggles cheap.
import { useState } from 'react';

import { useEvents, useLiveEvents, useSimulation } from '../api/queries';
import type { EventRow } from '../api/types';
import { useViewStore } from '../state/viewStore';

const LIMIT = 200;
const POLL_INTERVAL_MS = 500;

export function EventLog() {
  const selectedAgentId = useViewStore((s) => s.selectedAgentId);
  const [pinToSelected, setPinToSelected] = useState(false);
  const sim = useSimulation();
  const running = sim.data?.running ?? false;

  const pinned = pinToSelected && selectedAgentId !== null;

  // Global feed: share the composite cache. Filtered feed: own query,
  // gated on running so a paused sim produces zero traffic.
  const live = useLiveEvents({ enabled: !pinned });
  const filtered = useEvents(
    pinned ? { agent_id: selectedAgentId!, limit: LIMIT } : {},
    {
      enabled: pinned,
      refetchInterval: running ? POLL_INTERVAL_MS : false,
    },
  );

  const active = pinned ? filtered : live;
  // Render in server order (oldest → newest). Newest-on-top visual is
  // handled by `flex-direction: column-reverse` on `.eventlog`. This
  // keeps the DOM insertion order stable so role="log" +
  // aria-relevant="additions" announce only *new* rows to screen
  // readers instead of treating every reshuffled item as an addition.
  const rows = active.data ?? [];

  return (
    <section className="panel panel--grow">
      <div className="panel__head">
        <span className="panel__dot panel__dot--cyan" />
        <h2 className="panel__title">Events</h2>
        <label className="toggle" title="filter by selected agent">
          <input
            type="checkbox"
            checked={pinToSelected}
            onChange={(e) => setPinToSelected(e.target.checked)}
            disabled={selectedAgentId === null}
          />
          <span>selected only</span>
        </label>
      </div>

      {active.isLoading && <p className="eventlog__empty">loading…</p>}
      {!active.isLoading && rows.length === 0 && (
        <p className="eventlog__empty">no events yet — advance the sim</p>
      )}

      {rows.length > 0 && (
        // role="log" implies aria-live="polite" + aria-relevant="additions
        // text" per ARIA 1.2. Explicit duplicates removed — a single
        // attribute is easier to reason about and avoids SR double-reads.
        <ul className="eventlog" role="log" aria-label="simulation events">
          {rows.map((ev, i) => (
            <li key={`${ev.tick}-${ev.agent_id ?? 'x'}-${i}`} className="eventlog__row">
              <span className="eventlog__tick">t{ev.tick}</span>
              <span className={`eventlog__type eventlog__type--${typeClass(ev.type)}`}>
                {ev.type}
              </span>
              <span className="eventlog__body">{eventLabel(ev)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

// A readable one-liner for an event. Prefers the backend `description`
// when present; falls back to minimal `data` rendering so unknown
// event types still read as something.
function eventLabel(ev: EventRow): string {
  if (ev.description) return ev.description;
  if (ev.agent_id !== null) return `agent #${ev.agent_id}`;
  if (ev.data && typeof ev.data === 'object') {
    return Object.entries(ev.data as Record<string, unknown>)
      .map(([k, v]) => `${k}=${String(v)}`)
      .join(' ');
  }
  return '';
}

// Map event-type string to a CSS modifier so we can colour-code the
// feed without hard-coding styles per type. Unknown types fall through
// to the neutral tone — new engine event types don't require a CSS
// change to appear in the log.
function typeClass(type: string): string {
  if (type.includes('died') || type.includes('death')) return 'bad';
  if (type.includes('forage') || type.includes('ate')) return 'good';
  if (type.includes('social')) return 'warm';
  if (type.includes('move') || type.includes('explore')) return 'cool';
  return 'neutral';
}
