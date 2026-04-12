// Scrollable feed of recent sim events.
//
// Two modes:
//   - Global: last N events across all agents.
//   - Per-agent: filtered to the selected agent.
//
// Data source: `useEvents` with filter derived from the view store.
// The query key includes the filter, so toggling per-agent is a cache
// swap, not a refetch-and-re-render storm.
//
// Budget: `limit: 200` today. If we eventually run sims with millions
// of events, swap `useQuery` for `useInfiniteQuery` here — the API
// already supports `since_tick` for cursor-style pagination.
import { useMemo, useState } from 'react';

import { useEvents } from '../api/queries';
import type { EventRow } from '../api/types';
import { useViewStore } from '../state/viewStore';

const LIMIT = 200;

export function EventLog() {
  const selectedAgentId = useViewStore((s) => s.selectedAgentId);
  const [pinToSelected, setPinToSelected] = useState(false);

  const filter = useMemo(() => {
    if (pinToSelected && selectedAgentId !== null) {
      return { agent_id: selectedAgentId, limit: LIMIT };
    }
    return { limit: LIMIT };
  }, [pinToSelected, selectedAgentId]);

  const events = useEvents(filter);
  // API returns oldest first (ascending by tick); reverse for a
  // newsfeed feel — newest on top.
  const rows = useMemo(() => [...(events.data ?? [])].reverse(), [events.data]);

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

      {events.isLoading && <p className="eventlog__empty">loading…</p>}
      {!events.isLoading && rows.length === 0 && (
        <p className="eventlog__empty">no events yet — advance the sim</p>
      )}

      {rows.length > 0 && (
        <ul className="eventlog">
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
