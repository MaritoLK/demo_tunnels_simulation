import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';

import { ColonyPanel } from './ColonyPanel';

const COLONIES = [
  { id: 1, name: 'Red',  color: '#e74c3c', camp_x: 3,  camp_y: 3,  food_stock: 18, growing_count: 2 },
  { id: 2, name: 'Blue', color: '#3498db', camp_x: 16, camp_y: 3,  food_stock: 9,  growing_count: 1 },
];

describe('ColonyPanel', () => {
  it('renders one row per colony', () => {
    render(<ColonyPanel colonies={COLONIES} />);
    expect(screen.getByText('Red')).toBeInTheDocument();
    expect(screen.getByText('Blue')).toBeInTheDocument();
  });

  it('shows food_stock and growing_count', () => {
    render(<ColonyPanel colonies={COLONIES} />);
    expect(screen.getByText(/food 18/)).toBeInTheDocument();
    expect(screen.getByText(/fields 2/)).toBeInTheDocument();
  });

  it('renders nothing when colonies list is empty', () => {
    const { container } = render(<ColonyPanel colonies={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
