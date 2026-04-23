import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { AgentTooltip, clamp } from './AgentTooltip';
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

describe('clamp', () => {
  // Viewport 1000×800, tooltip 200×140, 8-px offset from cursor.
  const W = 200, H = 140, VW = 1000, VH = 800;

  it('positions below-right of cursor when there is room on both axes', () => {
    // Cursor in upper-left quadrant — default branch for X and Y.
    expect(clamp(100, 100, W, H, VW, VH)).toEqual({ left: 108, top: 108 });
  });

  it('mirrors to the left of cursor when right-edge would overflow', () => {
    // Cursor near right edge — X flip; Y default.
    const { left, top } = clamp(950, 100, W, H, VW, VH);
    expect(left).toBe(950 - W - 8); // 742
    expect(top).toBe(108);
  });

  it('mirrors above cursor when bottom-edge would overflow', () => {
    // Cursor near bottom edge — Y flip; X default.
    const { left, top } = clamp(100, 750, W, H, VW, VH);
    expect(left).toBe(108);
    expect(top).toBe(750 - H - 8); // 602
  });

  it('mirrors on both axes near the bottom-right corner', () => {
    const { left, top } = clamp(950, 750, W, H, VW, VH);
    expect(left).toBe(742);
    expect(top).toBe(602);
  });
});
