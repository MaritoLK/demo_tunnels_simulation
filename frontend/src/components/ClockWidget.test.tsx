import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { ClockWidget } from './ClockWidget';

describe('ClockWidget', () => {
  it('renders day and phase', () => {
    render(<ClockWidget day={3} phase="dusk" tick={78} />);
    expect(screen.getByText(/Day 3/)).toBeInTheDocument();
    expect(screen.getByText(/Dusk/i)).toBeInTheDocument();
  });

  it('shows phase progress', () => {
    // tick 78 → 78 % 30 = 18 of 30
    render(<ClockWidget day={3} phase="dusk" tick={78} />);
    expect(screen.getByText('18/30')).toBeInTheDocument();
  });
});
