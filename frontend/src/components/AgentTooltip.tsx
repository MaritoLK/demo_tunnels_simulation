import { STATE_ICON_MAP } from '../render/animConfig';
import type { Agent, Colony } from '../api/types';

const CARRY_MAX = 8;

interface Props {
  agent: Agent;
  colony: Colony | undefined;
  screenX: number;
  screenY: number;
}

function clamp(
  x: number, y: number,
  width: number, height: number,
  viewportW: number, viewportH: number,
): { left: number; top: number } {
  const left = x + width + 8 > viewportW ? x - width - 8 : x + 8;
  const top = y + height + 8 > viewportH ? y - height - 8 : y + 8;
  return { left, top };
}

function MiniBar({ label, value }: { label: string; value: number }) {
  const filled = Math.max(0, Math.min(8, Math.round((value / 100) * 8)));
  const bar = '█'.repeat(filled) + '░'.repeat(8 - filled);
  return (
    <div className="agent-tooltip__meter">
      <span className="agent-tooltip__meter-label">{label}</span>
      <span className="agent-tooltip__meter-bar">{bar}</span>
      <span className="agent-tooltip__meter-value">{Math.round(value)}</span>
    </div>
  );
}

// Rough dimensions — clamp uses an estimate so first-render positions
// reasonably. Real width/height could be measured post-mount with a ref
// for pixel accuracy, but 200×140 covers the common layout.
const TOOLTIP_W = 200;
const TOOLTIP_H = 140;

export function AgentTooltip({ agent, colony, screenX, screenY }: Props) {
  const viewportW = typeof window !== 'undefined' ? window.innerWidth : 1920;
  const viewportH = typeof window !== 'undefined' ? window.innerHeight : 1080;
  const { left, top } = clamp(
    screenX, screenY,
    TOOLTIP_W, TOOLTIP_H,
    viewportW, viewportH,
  );
  const glyph = STATE_ICON_MAP[agent.state] ?? '';
  const cargo = agent.cargo ?? 0;

  return (
    <div className="agent-tooltip" style={{ left, top }}>
      <div className="agent-tooltip__head">
        <span className="agent-tooltip__name">{agent.name}</span>
        {colony && (
          <span className="agent-tooltip__pill" style={{ background: colony.color }}>
            {colony.name}
          </span>
        )}
      </div>
      <div className="agent-tooltip__state">
        {glyph && <span className="agent-tooltip__icon">{glyph}</span>}
        <span>{agent.state}</span>
      </div>
      <div className="agent-tooltip__bars">
        <MiniBar label="hunger" value={agent.hunger} />
        <MiniBar label="energy" value={agent.energy} />
        <MiniBar label="social" value={agent.social} />
        <MiniBar label="health" value={agent.health} />
      </div>
      {cargo > 0 && (
        <div className="agent-tooltip__cargo">
          cargo {cargo.toFixed(1)} / {CARRY_MAX}
        </div>
      )}
      {agent.decision_reason && (
        <div className="agent-tooltip__reason">{agent.decision_reason}</div>
      )}
    </div>
  );
}
