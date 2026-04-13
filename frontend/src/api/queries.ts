// React Query hooks.
//
// §9.27 architecture shift: the backend now runs a background tick loop.
// The frontend polls ONE composite endpoint (`/world/state`) instead of
// fetching sim/world/agents/events separately — same wall-clock latency
// for every consumer and one nginx cache entry serves N viewers.
//
// Shape:
//   useWorldState() — the base polling hook. Gates refetchInterval on
//                     sim.running so a paused sim produces zero polling
//                     traffic. Resuming the sim restarts polling on the
//                     next render.
//   useSimulation, useWorld, useAgents — `select`-based slices of the
//                     same cache. Consumers keep their existing data
//                     shape; under the hood every hook shares the one
//                     query, one cache entry, one network request.
//   useEvents — standalone query for filtered history (agent detail
//               panel). The composite endpoint supplies the live log,
//               so this hook is reserved for explicit filtered queries.
//
// Mutations invalidate `['worldState']` — the one key all slices read
// from — so create/step fire a single refetch instead of four.
import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryOptions,
} from '@tanstack/react-query';

import { ApiError, apiGet, apiSend } from './client';
import type {
  Agent,
  EventRow,
  SimControlUpdate,
  SimulationSummary,
  WorldSnapshot,
  WorldStateResponse,
} from './types';

const WORLD_STATE_KEY = ['worldState'] as const;

// How often to poll /world/state while the sim is running. 500ms matches
// the brief and, paired with the nginx 1s micro-cache (§9.27d; nginx
// requires integer-second TTL), means roughly every second poll is a
// cache hit — DB sees ~1 req/s/sim regardless of viewer count.
const POLL_INTERVAL_MS = 500;

function isNotFound(err: unknown): boolean {
  return err instanceof ApiError && err.status === 404;
}

// One place that builds the base query config. All slice hooks spread
// this so they share the cache + polling behaviour.
function worldStateQuery(): UseQueryOptions<WorldStateResponse> {
  return {
    queryKey: WORLD_STATE_KEY as unknown as readonly unknown[],
    queryFn: () => apiGet<WorldStateResponse>('/world/state'),
    refetchInterval: (query) => {
      const running = query.state.data?.sim?.running;
      return running ? POLL_INTERVAL_MS : false;
    },
    retry: (failureCount, err) => (isNotFound(err) ? false : failureCount < 2),
  };
}

export function useWorldState(
  opts?: Omit<UseQueryOptions<WorldStateResponse>, 'queryKey' | 'queryFn'>,
) {
  return useQuery<WorldStateResponse>({ ...worldStateQuery(), ...opts });
}

export function useSimulation(
  opts?: Omit<UseQueryOptions<WorldStateResponse, Error, SimulationSummary>, 'queryKey' | 'queryFn'>,
) {
  return useQuery<WorldStateResponse, Error, SimulationSummary>({
    ...worldStateQuery(),
    select: (d) => d.sim,
    ...opts,
  });
}

export function useWorld(
  opts?: Omit<UseQueryOptions<WorldStateResponse, Error, WorldSnapshot>, 'queryKey' | 'queryFn'>,
) {
  return useQuery<WorldStateResponse, Error, WorldSnapshot>({
    ...worldStateQuery(),
    select: (d) => d.world,
    ...opts,
  });
}

export function useAgents(
  opts?: Omit<UseQueryOptions<WorldStateResponse, Error, Agent[]>, 'queryKey' | 'queryFn'>,
) {
  return useQuery<WorldStateResponse, Error, Agent[]>({
    ...worldStateQuery(),
    select: (d) => d.agents,
    ...opts,
  });
}

// Live event log slice — reads the `events` array that the composite
// endpoint populates with the most recent N events. Separate hook rather
// than inlining in EventLog so callers stay terse.
export function useLiveEvents(
  opts?: Omit<UseQueryOptions<WorldStateResponse, Error, EventRow[]>, 'queryKey' | 'queryFn'>,
) {
  return useQuery<WorldStateResponse, Error, EventRow[]>({
    ...worldStateQuery(),
    select: (d) => d.events,
    ...opts,
  });
}

export interface EventFilter {
  agent_id?: number;
  since_tick?: number;
  limit?: number;
}

// Filtered events (e.g. per-agent history) — lives outside the composite
// endpoint because filters are consumer-specific.
//
// placeholderData: keepPreviousData — when EventLog toggles between
// global and per-agent mode, the filter changes and the query key
// changes. Without this, React Query flips `data` to `undefined` while
// the new key fetches, and the EventLog renders its "loading…" empty
// state for a beat. keepPreviousData keeps the old rows visible until
// the new ones arrive, so the toggle feels instant. See §9.29-F1.
export function useEvents(
  filter: EventFilter = {},
  opts?: Omit<UseQueryOptions<EventRow[]>, 'queryKey' | 'queryFn'>,
) {
  const qs = new URLSearchParams();
  if (filter.agent_id !== undefined) qs.set('agent_id', String(filter.agent_id));
  if (filter.since_tick !== undefined) qs.set('since_tick', String(filter.since_tick));
  if (filter.limit !== undefined) qs.set('limit', String(filter.limit));
  const suffix = qs.toString() ? `?${qs.toString()}` : '';
  return useQuery<EventRow[]>({
    queryKey: ['events', filter],
    queryFn: async () => {
      const res = await apiGet<{ events: EventRow[] }>(`/events${suffix}`);
      return res.events;
    },
    placeholderData: keepPreviousData,
    ...opts,
  });
}

export interface CreateSimArgs {
  width: number;
  height: number;
  seed?: number;
  agent_count?: number;
}

export function useCreateSimulation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (args: CreateSimArgs) =>
      apiSend<SimulationSummary>('PUT', '/simulation', args),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: WORLD_STATE_KEY });
      qc.invalidateQueries({ queryKey: ['events'] });
    },
  });
}

export function useStepSimulation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (ticks: number) =>
      apiSend<{ tick: number; events: EventRow[] }>('POST', '/simulation/step', { ticks }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: WORLD_STATE_KEY });
      qc.invalidateQueries({ queryKey: ['events'] });
    },
  });
}

// Start/stop/speed control. Mutation rather than hook-owned state so the
// button + slider can fire it and React Query handles the pending/error
// UI. On success, invalidate `worldState` so the UI reflects the new
// control flags without waiting for the next poll.
export function useSimControl() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (update: SimControlUpdate) =>
      apiSend<{ running: boolean; speed: number }>('PATCH', '/simulation/control', update),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: WORLD_STATE_KEY });
    },
  });
}
