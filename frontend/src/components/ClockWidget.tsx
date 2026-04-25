import { TICKS_PER_PHASE, type Phase } from '../api/types';

const PHASE_GLYPH: Record<Phase, string> = {
  dawn: '🌅',
  day: '☀️',
  dusk: '🌆',
  night: '🌙',
};

export function ClockWidget({
  day, phase, tick,
}: { day: number; phase: Phase; tick: number }) {
  const progress = tick % TICKS_PER_PHASE;
  const bar = '▓'.repeat(progress) + '░'.repeat(TICKS_PER_PHASE - progress);
  return (
    <div className="clock-widget" data-phase={phase}>
      <div className="clock-widget__main">
        <span className="clock-widget__glyph">{PHASE_GLYPH[phase]}</span>
        <span>Day {day}</span>
        <span className="clock-widget__sep">·</span>
        <span className="clock-widget__phase">
          {phase[0].toUpperCase() + phase.slice(1)}
        </span>
      </div>
      <div className="clock-widget__bar">
        <span className="clock-widget__bar-fill">{bar}</span>
        <span className="clock-widget__bar-count">{progress}/{TICKS_PER_PHASE}</span>
      </div>
    </div>
  );
}
