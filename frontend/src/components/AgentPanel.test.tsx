import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { AgentPanel } from './AgentPanel';
import { useViewStore } from '../state/viewStore';
import type { Agent } from '../api/types';

const baseAgent: Agent = {
  id: 1, name: 'Alice', x: 2, y: 2, state: 'foraging',
  hunger: 47, energy: 80, social: 65, health: 90, age: 12,
  alive: true, colony_id: 1, rogue: false, loner: false, cargo: 2.5,
  decision_reason: 'hunger < 50 → forage',
};

function mountWith(agent: Agent) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  // Seed the composite worldState query cache. The panel's useAgents()
  // reads .agents from this. Unused branches (sim/world/etc.) are null
  // since the panel doesn't touch them.
  qc.setQueryData(['worldState'], {
    sim: null, world: null, agents: [agent], colonies: [], events: [],
  });
  // Pick this agent via the view store.
  useViewStore.getState().selectAgent(agent.id);

  return render(
    <QueryClientProvider client={qc}>
      <AgentPanel />
    </QueryClientProvider>,
  );
}

describe('AgentPanel decision_reason', () => {
  beforeEach(() => {
    useViewStore.getState().selectAgent(null);   // reset between tests
  });

  it('renders decision_reason below the state pill when non-empty', () => {
    mountWith(baseAgent);
    expect(screen.getByText('hunger < 50 → forage')).toBeInTheDocument();
  });

  it('hides decision_reason when empty string', () => {
    mountWith({ ...baseAgent, decision_reason: '' });
    expect(screen.queryByText(/→/)).not.toBeInTheDocument();
  });
});
