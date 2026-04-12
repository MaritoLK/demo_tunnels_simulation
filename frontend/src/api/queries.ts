// React Query hooks. Each hook owns a cache key, so mutations that
// affect the world (create, step) can invalidate the right slice.
//
// Why React Query:
//   - Generational sim will produce event streams that dwarf a single
//     useState snapshot. `useInfiniteQuery` is the right shape for that.
//   - Background refetch + staleTime lets the UI poll without flicker.
//   - Mutation → invalidation is one line; the alternative is manual
//     "now refetch everything" plumbing in every handler.
//
// Key convention: ['world'], ['agents'], ['sim'], ['events', filters].
// If we later switch to SSE/WebSocket, these hooks stay; only the
// transport in api/client.ts changes.
import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryOptions,
} from '@tanstack/react-query';

import { apiGet, apiSend } from './client';
import type {
  Agent,
  EventRow,
  SimulationSummary,
  WorldSnapshot,
} from './types';

export function useSimulation(
  opts?: Omit<UseQueryOptions<SimulationSummary>, 'queryKey' | 'queryFn'>,
) {
  return useQuery<SimulationSummary>({
    queryKey: ['sim'],
    queryFn: () => apiGet<SimulationSummary>('/simulation'),
    // Retry-on-404 would be wrong — a cold DB legitimately has no sim.
    // Let the 404 propagate as error state; the UI shows a "create" button.
    retry: (failureCount, err: unknown) => {
      if (err && typeof err === 'object' && 'status' in err && (err as { status: number }).status === 404) {
        return false;
      }
      return failureCount < 2;
    },
    ...opts,
  });
}

export function useWorld(
  opts?: Omit<UseQueryOptions<WorldSnapshot>, 'queryKey' | 'queryFn'>,
) {
  return useQuery<WorldSnapshot>({
    queryKey: ['world'],
    queryFn: () => apiGet<WorldSnapshot>('/world'),
    ...opts,
  });
}

export function useAgents(
  opts?: Omit<UseQueryOptions<Agent[]>, 'queryKey' | 'queryFn'>,
) {
  return useQuery<Agent[]>({
    queryKey: ['agents'],
    queryFn: async () => {
      const res = await apiGet<{ agents: Agent[] }>('/agents');
      return res.agents;
    },
    ...opts,
  });
}

export interface EventFilter {
  agent_id?: number;
  since_tick?: number;
  limit?: number;
}

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
      // Everything world-derived is stale after a (re)create.
      qc.invalidateQueries({ queryKey: ['sim'] });
      qc.invalidateQueries({ queryKey: ['world'] });
      qc.invalidateQueries({ queryKey: ['agents'] });
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
      // World tiles may have had resource_amount decremented on forage;
      // agents moved; events appended. Invalidate all three.
      qc.invalidateQueries({ queryKey: ['sim'] });
      qc.invalidateQueries({ queryKey: ['world'] });
      qc.invalidateQueries({ queryKey: ['agents'] });
      qc.invalidateQueries({ queryKey: ['events'] });
    },
  });
}
