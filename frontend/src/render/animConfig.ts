// Per-agent animation and icon constants. Kept in one module so
// renderer + any future debug UI read from the same source.

// 10 fps — feels alive without distracting. Matches Tiny Swords' own
// demo timing.
export const FRAME_MS = 100;

// Each pawn sheet is 1536×192 = 8 frames of 192×192.
export const FRAMES_PER_CYCLE = 8;

// State icons rendered above each agent on the canvas. IDLE gets an
// empty string — renderer guards against fillText('') because the
// default state between decisions is "nothing to say."
// See spec §State icon overlay for the definitive engine state list.
export const STATE_ICON_MAP: Record<string, string> = {
  idle:         '',
  resting:      '💤',
  foraging:     '🌾',
  socialising:  '💬',
  exploring:    '·',
  traversing:   '…',
  planting:     '🌱',
  harvesting:   '🌾',
  depositing:   '📦',
  eating:       '🍖',
  dead:         '☠',
};
