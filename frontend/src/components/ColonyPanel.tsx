import type { Colony } from '../api/types';
import { MAX_COLONY_TIER, UPGRADE_TIER_COSTS } from '../api/types';

export function ColonyPanel({ colonies }: { colonies: Colony[] }) {
  if (colonies.length === 0) return null;
  return (
    <section className="panel colony-panel">
      <div className="panel__head">
        <span className="panel__dot" />
        <h2 className="panel__title">Colonies</h2>
      </div>
      {colonies.map((c) => {
        const tier = c.tier ?? 0;
        const wood = Math.floor(c.wood_stock ?? 0);
        const stone = Math.floor(c.stone_stock ?? 0);
        const atMax = tier >= MAX_COLONY_TIER;
        const next = atMax ? null : UPGRADE_TIER_COSTS[tier + 1];
        return (
          <div key={c.id} className="colony-row">
            <span
              className="colony-row__swatch"
              style={{ backgroundColor: c.color }}
              aria-hidden
            />
            <span className="colony-row__name">{c.name}</span>
            <span className="colony-row__stat">tier {tier}</span>
            <span className="colony-row__stat">food {Math.floor(c.food_stock)}</span>
            <span className="colony-row__stat">wood {wood}</span>
            <span className="colony-row__stat">stone {stone}</span>
            <span className="colony-row__stat">fields {c.growing_count}</span>
            {next && (
              // Upgrade requirements indicator — shows the gap between
              // current stockpiles and the next tier's costs so the
              // demo viewer can read "how close is the next upgrade?"
              // at a glance. Hidden once the colony reaches the cap.
              <span className="colony-row__upgrade">
                next:{' '}
                <span className={wood >= next.wood ? 'colony-row__met' : ''}>
                  {wood}/{next.wood} 🪵
                </span>
                {' '}
                <span className={stone >= next.stone ? 'colony-row__met' : ''}>
                  {stone}/{next.stone} ⛰
                </span>
              </span>
            )}
            {atMax && <span className="colony-row__stat">— max tier</span>}
          </div>
        );
      })}
    </section>
  );
}
