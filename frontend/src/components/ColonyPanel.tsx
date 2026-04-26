import type { Colony } from '../api/types';

export function ColonyPanel({ colonies }: { colonies: Colony[] }) {
  if (colonies.length === 0) return null;
  return (
    <section className="panel colony-panel">
      <div className="panel__head">
        <span className="panel__dot" />
        <h2 className="panel__title">Colonies</h2>
      </div>
      {colonies.map((c) => (
        <div key={c.id} className="colony-row">
          <span
            className="colony-row__swatch"
            style={{ backgroundColor: c.color }}
            aria-hidden
          />
          <span className="colony-row__name">{c.name}</span>
          <span className="colony-row__stat">tier {c.tier ?? 0}</span>
          <span className="colony-row__stat">food {Math.floor(c.food_stock)}</span>
          <span className="colony-row__stat">wood {Math.floor(c.wood_stock ?? 0)}</span>
          <span className="colony-row__stat">stone {Math.floor(c.stone_stock ?? 0)}</span>
          <span className="colony-row__stat">fields {c.growing_count}</span>
        </div>
      ))}
    </section>
  );
}
