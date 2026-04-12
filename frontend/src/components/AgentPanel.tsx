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
            {agent.alive ? agent.state : 'deceased'}
          </span>
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
      </div>
    </section>
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
