// Detail readout for the currently selected agent.
//
// Data source: the same `useAgents` cache the canvas draws from. By
// reading from React Query here too, the panel and the canvas can
// never disagree — both are views over one cache entry.
//
// Shape: the panel renders inline in the sidebar. It only mounts when
// an agent is selected; `selectAgent(null)` unmounts it. This keeps
// the sidebar calm when nothing is picked and turns selection into
// the user's mental "open the inspector" gesture.
import { useAgents } from '../api/queries';
import { useViewStore } from '../state/viewStore';
import { STATE_VISUALS } from '../render/animConfig';
import { CARRY_MAX } from '../api/types';

export function AgentPanel() {
  const selectedAgentId = useViewStore((s) => s.selectedAgentId);
  const selectAgent = useViewStore((s) => s.selectAgent);
  const agents = useAgents();

  if (selectedAgentId === null) return null;
  const agent = agents.data?.find((a) => a.id === selectedAgentId);
  if (!agent) return null;

  return (
    <section className="panel">
      <div className="panel__head">
        <span className="panel__dot panel__dot--rose" />
        <h2 className="panel__title">{agent.name}</h2>
        <button
          className="panel__close"
          onClick={() => selectAgent(null)}
          aria-label="close agent panel"
        >
          ✕
        </button>
      </div>

      <dl className="readout">
        <dt>id</dt>
        <dd>#{agent.id}</dd>
        <dt>state</dt>
        <dd>
          <span className={`pill ${agent.alive ? 'pill--alive' : 'pill--dead'}`}>
            {STATE_VISUALS[agent.state]?.glyph ?? ''} {agent.alive ? agent.state : 'deceased'}
          </span>
          {agent.alive && agent.rogue && (
            <span
              className="pill"
              style={{ marginLeft: 6, background: '#4a1a1a', color: '#ff8f6b' }}
              title="Social need collapsed to zero — cannot return home"
            >
              rogue
            </span>
          )}
          {agent.alive && agent.loner && !agent.rogue && (
            <span
              className="pill"
              style={{ marginLeft: 6, background: '#1f2933', color: '#9fb4d0' }}
              title="Social need decays faster than normal"
            >
              loner
            </span>
          )}
          {agent.decision_reason && (
            <div className="decision-reason">{agent.decision_reason}</div>
          )}
        </dd>
        <dt>position</dt>
        <dd>({agent.x}, {agent.y})</dd>
        <dt>age</dt>
        <dd>{agent.age}</dd>
      </dl>

      <div className="meters">
        <Meter label="health" value={agent.health} hue={healthHue(agent.health)} />
        <Meter label="hunger" value={agent.hunger} hue={needHue(agent.hunger)} />
        <Meter label="energy" value={agent.energy} hue={needHue(agent.energy)} />
        <Meter label="social" value={agent.social} hue={needHue(agent.social)} />
        <CargoMeter
          food={agent.cargo_food ?? 0}
          wood={agent.cargo_wood ?? 0}
          stone={agent.cargo_stone ?? 0}
        />
      </div>
    </section>
  );
}

// Pouch fullness. Scale is 0..CARRY_MAX (weight units, not 0..100 like
// needs). Weight = food*1 + wood*2 + stone*3, so the meter shows the
// total + a per-resource breakdown so the demo viewer can read at a
// glance whether the agent is hauling food, lumber, or stone.
function CargoMeter({ food, wood, stone }: { food: number; wood: number; stone: number }) {
  const weight = food * 1 + wood * 2 + stone * 3;
  const clamped = Math.max(0, Math.min(CARRY_MAX, weight));
  const pct = (clamped / CARRY_MAX) * 100;
  const parts: string[] = [];
  if (food > 0) parts.push(`🍎 ${food.toFixed(0)}`);
  if (wood > 0) parts.push(`🪵 ${wood.toFixed(0)}`);
  if (stone > 0) parts.push(`⛰ ${stone.toFixed(0)}`);
  return (
    <div className="meter">
      <div className="meter__row">
        <span className="meter__label">cargo</span>
        <span className="meter__value">
          {clamped.toFixed(1)} / {CARRY_MAX}
          {parts.length > 0 && <> · {parts.join(' ')}</>}
        </span>
      </div>
      <div className="meter__track">
        <div
          className="meter__fill"
          style={{ width: `${pct}%`, background: '#ff7b3b' }}
        />
      </div>
    </div>
  );
}

// A compact horizontal bar. 0..100 → 0..100% fill. Hue is passed in so
// the meter is purely presentational — semantic mapping lives above.
function Meter({ label, value, hue }: { label: string; value: number; hue: number }) {
  const clamped = Math.max(0, Math.min(100, value));
  return (
    <div className="meter">
      <div className="meter__row">
        <span className="meter__label">{label}</span>
        <span className="meter__value">{Math.round(clamped)}</span>
      </div>
      <div className="meter__track">
        <div
          className="meter__fill"
          style={{
            width: `${clamped}%`,
            background: `hsl(${hue}, 70%, 55%)`,
          }}
        />
      </div>
    </div>
  );
}

// 0..100 → red..green, same scheme as the canvas agent body. Keeps
// "this agent's dot looks orange" and "health meter is orange" aligned.
function healthHue(v: number): number {
  return Math.max(0, Math.min(120, (v / 100) * 120));
}

// Needs (hunger/energy/social) all decay toward 0 in the engine, so
// "high is healthy". Same 0..120° hue curve as healthHue — a low need
// reads red, a full need reads green.
function needHue(v: number): number {
  return Math.max(0, Math.min(120, (v / 100) * 120));
}
