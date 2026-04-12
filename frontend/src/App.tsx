import { useEffect, useRef, useState } from 'react';

import { useCreateSimulation, useSimulation, useStepSimulation } from './api/queries';
import { AgentPanel } from './components/AgentPanel';
import { EmptyState } from './components/EmptyState';
import { EventLog } from './components/EventLog';
import { WorldCanvas } from './components/WorldCanvas';

export function App() {
  const sim = useSimulation();
  const createSim = useCreateSimulation();
  const stepSim = useStepSimulation();

  const [width, setWidth] = useState(40);
  const [height, setHeight] = useState(25);
  const [seed, setSeed] = useState(42);
  const [agentCount, setAgentCount] = useState(5);
  const [steps, setSteps] = useState(1);

  // Tick pulse — the one bit of attention-grabbing motion. Everything else
  // in the HUD is calm; the tick number flashes hot-coral for 420ms when
  // the sim advances, so the user's eye catches the change.
  const [tickPulse, setTickPulse] = useState(false);
  const prevTick = useRef<number | null>(null);
  useEffect(() => {
    const t = sim.data?.tick ?? null;
    if (t !== null && prevTick.current !== null && t !== prevTick.current) {
      setTickPulse(true);
      const id = setTimeout(() => setTickPulse(false), 420);
      return () => clearTimeout(id);
    }
    prevTick.current = t;
  }, [sim.data?.tick]);

  const simStatus = getSimStatus(sim);

  return (
    <div className="shell">
      <aside className="shell__aside">
        <header className="mast">
          <div className="mast__sigil">T</div>
          <div>
            <h1 className="mast__title">Tunnels</h1>
            <div className="mast__sub">colony sandbox</div>
          </div>
        </header>

        <section className="panel">
          <div className="panel__head">
            <span className="panel__dot" />
            <h2 className="panel__title">New World</h2>
          </div>
          <LabeledNumber label="width" value={width} onChange={setWidth} />
          <LabeledNumber label="height" value={height} onChange={setHeight} />
          <LabeledNumber label="seed" value={seed} onChange={setSeed} />
          <LabeledNumber label="agents" value={agentCount} onChange={setAgentCount} />
          <button
            className="btn btn--primary"
            onClick={() => createSim.mutate({ width, height, seed, agent_count: agentCount })}
            disabled={createSim.isPending}
          >
            <span className="btn__ico">✦</span>
            {createSim.isPending ? 'Generating…' : 'Generate World'}
          </button>
        </section>

        <section className="panel">
          <div className="panel__head">
            <span className="panel__dot panel__dot--cyan" />
            <h2 className="panel__title">Simulate</h2>
          </div>
          <LabeledNumber label="ticks" value={steps} onChange={setSteps} />
          <button
            className="btn"
            onClick={() => stepSim.mutate(steps)}
            disabled={stepSim.isPending || simStatus !== 'ok'}
          >
            <span className="btn__ico">▶</span>
            {stepSim.isPending ? 'Running…' : `Advance ${steps}`}
          </button>
        </section>

        <section className="panel">
          <div className="panel__head">
            <span className="panel__dot panel__dot--lime" />
            <h2 className="panel__title">World Stats</h2>
          </div>
          {simStatus === 'ok' && sim.data && (
            <dl className="readout">
              <dt>size</dt><dd>{sim.data.width} × {sim.data.height}</dd>
              <dt>seed</dt><dd>{sim.data.seed ?? '—'}</dd>
              <dt>population</dt>
              <dd>
                <span className="pill pill--alive">{sim.data.alive_count} alive</span>
              </dd>
              <dt>total</dt><dd>{sim.data.agent_count}</dd>
              <dt>status</dt>
              <dd>
                <span className={`pill ${sim.data.running ? 'pill--alive' : 'pill--idle'}`}>
                  {sim.data.running ? 'running' : 'paused'}
                </span>
              </dd>
            </dl>
          )}
          {simStatus === 'none' && (
            <p className="readout"><span className="state--none">generate a world to begin</span></p>
          )}
          {simStatus === 'loading' && (
            <p className="readout"><span className="state--none">loading…</span></p>
          )}
          {simStatus === 'error' && (
            <p className="readout"><span className="state--error">connection error</span></p>
          )}
        </section>

        <AgentPanel />

        <EventLog />
      </aside>

      <main className="shell__main">
        <header className="hud">
          <div className="hud__tick">
            <span className="hud__tick-label">Tick</span>
            <span className={`hud__tick-value ${tickPulse ? 'hud__tick-value--pulse' : ''}`}>
              {sim.data ? fmtNum(sim.data.tick) : '—'}
            </span>
          </div>

          <div className="hud__badges">
            {sim.data && (
              <>
                <span className="badge">
                  <span className="badge__k">world</span>
                  <span className="badge__v">{sim.data.width}×{sim.data.height}</span>
                </span>
                <span className="badge">
                  <span className="badge__k">alive</span>
                  <span className="badge__v">{sim.data.alive_count}/{sim.data.agent_count}</span>
                </span>
                <span className="badge">
                  <span className="badge__k">seed</span>
                  <span className="badge__v">{sim.data.seed ?? '—'}</span>
                </span>
              </>
            )}
          </div>

          <div className="hud__status">
            <span className={`hud__status-dot ${
              simStatus === 'ok' ? 'hud__status-dot--ok' :
              simStatus === 'error' ? 'hud__status-dot--err' : ''
            }`} />
            {simStatus === 'ok' ? 'online' :
             simStatus === 'loading' ? 'sync' :
             simStatus === 'none' ? 'empty' : 'error'}
          </div>
        </header>

        <section className="observe">
          <div className="observe__frame">
            <div className="observe__glow" />
            <WorldCanvas />
            {simStatus === 'none' && <EmptyState />}
          </div>
        </section>
      </main>
    </div>
  );
}

type SimStatus = 'loading' | 'ok' | 'none' | 'error';

function getSimStatus(sim: { isLoading: boolean; error: unknown; data: unknown }): SimStatus {
  if (sim.isLoading) return 'loading';
  if (sim.error) {
    const e = sim.error as { status?: number };
    if (e && typeof e === 'object' && e.status === 404) return 'none';
    return 'error';
  }
  return 'ok';
}

function fmtNum(n: number): string {
  return new Intl.NumberFormat('en-US').format(n);
}

function LabeledNumber({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (n: number) => void;
}) {
  return (
    <label className="field">
      <span className="field__label">{label}</span>
      <input
        type="number"
        className="field__input"
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </label>
  );
}
