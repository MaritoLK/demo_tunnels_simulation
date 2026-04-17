// Inspector for the selected tile. Mirrors AgentPanel in structure so
// the UI feels consistent: one panel shape, content swaps based on
// which selection is active.
//
// Selection contract:
//   - selectedTile and selectedAgentId are mutually exclusive in the
//     viewStore — selecting one clears the other. So TilePanel and
//     AgentPanel will never both mount; no z-order or overlap concerns.
//   - We read the tile out of useWorld() so panel and canvas share one
//     cache entry (same pattern as AgentPanel ↔ useAgents).
import { useColonies, useWorld } from '../api/queries';
import { useViewStore } from '../state/viewStore';

// Duplicated from backend config.CROP_MATURE_TICKS. Small scalar, not
// worth a /config round-trip — same pattern as CARRY_MAX in AgentPanel.
const CROP_MATURE_TICKS = 60;

export function TilePanel() {
  const selectedTile = useViewStore((s) => s.selectedTile);
  const selectTile = useViewStore((s) => s.selectTile);
  const world = useWorld();
  const colonies = useColonies();

  if (!selectedTile) return null;
  const tile = world.data?.tiles[selectedTile.y]?.[selectedTile.x];
  if (!tile) return null;

  const owner = tile.crop_colony_id
    ? colonies.data?.find((c) => c.id === tile.crop_colony_id)
    : undefined;

  return (
    <section className="panel">
      <div className="panel__head">
        <span className="panel__dot" style={{ background: '#ffd23f' }} />
        <h2 className="panel__title">tile ({tile.x}, {tile.y})</h2>
        <button
          className="panel__close"
          onClick={() => selectTile(null)}
          aria-label="close tile panel"
        >
          ✕
        </button>
      </div>

      <dl className="readout">
        <dt>terrain</dt>
        <dd><span className="pill">{tile.terrain}</span></dd>
        {tile.crop_state !== 'none' && (
          <>
            <dt>crop</dt>
            <dd>
              <span
                className="pill"
                style={{
                  background: tile.crop_state === 'mature' ? '#3a2f10' : '#1a2d1a',
                  color: tile.crop_state === 'mature' ? '#ffd23f' : '#7ee070',
                }}
              >
                {tile.crop_state}
              </span>
            </dd>
            {owner && (
              <>
                <dt>planter</dt>
                <dd>
                  <span className="pill" style={{ background: owner.color, color: '#fff' }}>
                    {owner.name}
                  </span>
                </dd>
              </>
            )}
          </>
        )}
        {tile.resource_type === 'food' && tile.resource_amount > 0 && (
          <>
            <dt>food</dt>
            <dd>{tile.resource_amount.toFixed(1)} units</dd>
          </>
        )}
      </dl>

      {tile.crop_state === 'growing' && (
        <div className="meters">
          <div className="meter">
            <div className="meter__row">
              <span className="meter__label">growth</span>
              <span className="meter__value">
                {tile.crop_growth_ticks} / {CROP_MATURE_TICKS}
              </span>
            </div>
            <div className="meter__track">
              <div
                className="meter__fill"
                style={{
                  width: `${Math.min(100, (tile.crop_growth_ticks / CROP_MATURE_TICKS) * 100)}%`,
                  background: '#7ee070',
                }}
              />
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
