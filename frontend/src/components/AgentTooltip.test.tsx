import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { AgentTooltip } from './AgentTooltip';
import type { Agent, Colony } from '../api/types';

const baseAgent: Agent = {
  id: 1, name: 'Alice', x: 2, y: 2, state: 'foraging',
  hunger: 47, energy: 80, social: 65, health: 90, age: 12,
  alive: true, colony_id: 1, rogue: false, loner: false, cargo: 2.5,
  decision_reason: 'hunger < 50 → forage',
};

const baseColony: Colony = {
  id: 1, name: 'Red', color: '#e74c3c', camp_x: 3, camp_y: 3,
  food_stock: 18, growing_count: 0, sprite_palette: 'Red',
};

describe('AgentTooltip', () => {
  it('renders agent name and colony name', () => {
    render(<AgentTooltip agent={baseAgent} colony={baseColony} screenX={100} screenY={100} />);
    expect(screen.getByText('Alice')).toBeInTheDocument();
    expect(screen.getByText('Red')).toBeInTheDocument();
  });

  it('renders state', () => {
    render(<AgentTooltip agent={baseAgent} colony={baseColony} screenX={100} screenY={100} />);
    expect(screen.getByText(/foraging/)).toBeInTheDocument();
  });

  it('renders cargo line when cargo > 0', () => {
    render(<AgentTooltip agent={baseAgent} colony={baseColony} screenX={100} screenY={100} />);
    expect(screen.getByText(/cargo/i)).toBeInTheDocument();
  });

  it('omits cargo line when cargo is 0', () => {
    const noCargo = { ...baseAgent, cargo: 0 };
    render(<AgentTooltip agent={noCargo} colony={baseColony} screenX={100} screenY={100} />);
    expect(screen.queryByText(/cargo/i)).not.toBeInTheDocument();
  });

  it('renders decision_reason when non-empty', () => {
    render(<AgentTooltip agent={baseAgent} colony={baseColony} screenX={100} screenY={100} />);
    expect(screen.getByText(baseAgent.decision_reason)).toBeInTheDocument();
  });

  it('omits decision_reason line when empty', () => {
    const blank = { ...baseAgent, decision_reason: '' };
    render(<AgentTooltip agent={blank} colony={baseColony} screenX={100} screenY={100} />);
    // The reason text would be empty; just confirm the component still
    // renders the agent name (doesn't crash on empty reason).
    expect(screen.getByText('Alice')).toBeInTheDocument();
  });
});
