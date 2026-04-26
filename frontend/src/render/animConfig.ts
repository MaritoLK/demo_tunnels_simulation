// Per-agent animation and visual constants. Kept in one module so
// renderer + any future debug UI read from the same source.

// 10 fps — feels alive without distracting. Matches Tiny Swords' own
// demo timing.
export const FRAME_MS = 100;

// Each pawn sheet is 1536×192 = 8 frames of 192×192.
export const FRAMES_PER_CYCLE = 8;

// Per-state visual surface. One entry per engine state — single source
// of truth for the overhead glyph, the action label, and the label tint.
// Keys MUST match backend `actions.STATE_*` strings (wire contract).
//
// `glyph`  — overhead emoji/character drawn above the agent. Empty
//            string = no glyph (idle has nothing to say).
// `label`  — short word painted near the head ('forage', 'rest', ...).
//            Optional: dead agents skip the label entirely (the fade
//            already reads as "stopped").
// `color`  — paired with `label`; chosen to match the in-world signal
//            (food = coral, growth = green, gold = mature, etc.).
export interface StateVisual {
  glyph: string;
  label?: string;
  color?: string;
}

export const STATE_VISUALS: Record<string, StateVisual> = {
  idle:        { glyph: '',   label: 'idle',    color: '#8a8a93' }, // muted grey
  resting:     { glyph: '💤', label: 'rest',    color: '#6b9bd4' }, // sky blue — calm
  foraging:    { glyph: '🌾', label: 'forage',  color: '#ff7b3b' }, // coral — matches food sprite
  socialising: { glyph: '💬', label: 'social',  color: '#d870c9' }, // magenta — warmth
  exploring:   { glyph: '?',  label: 'explore', color: '#5cbd4a' }, // green — go
  traversing:  { glyph: '…',  label: 'trek',    color: '#c08a4a' }, // tan — terrain drag
  planting:    { glyph: '🌱', label: 'plant',   color: '#7ee070' }, // bright green — matches growing dot
  harvesting:  { glyph: '🌾', label: 'harvest', color: '#ffd23f' }, // gold — matches mature dot
  depositing:  { glyph: '📦', label: 'deposit', color: '#4ec9d4' }, // cyan — inflow
  eating:      { glyph: '🍖', label: 'eat',     color: '#ff6b8a' }, // pink-red — appetite
  dead:        { glyph: '☠'                                       }, // no label — fade reads as "stopped"
};
