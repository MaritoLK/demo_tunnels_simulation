# Agent Shine — Design Spec

**Date:** 2026-04-23
**Re-demo target:** 2026-04-28 (Tue, ~5 days)
**Scope bucket:** Round 3 (polish existing depth) of the post-cleanup enhancement plan.
**Approach:** Z — combined slice: animation + state icon + tooltip + decision reason.

## Goal

Individual agents read as *visibly distinct and self-explanatory* on canvas and in the inspector panel. Today a dot-with-sprite-frame-0 looks like noise that moves. After this round, a viewer should be able to say: *"That one's red, hauling food, heading to camp because hungry."*

## In scope

1. Per-agent animation cycling — idle 8-frame loop, run 8-frame loop.
2. Per-colony pawn color — Red / Blue / Purple / Yellow sprite sheets, selected by `colony.name`.
3. Cargo-aware sprite variant — `Pawn_Idle_Meat` / `Pawn_Run_Meat` when `agent.cargo > 0`.
4. State icon overlay on canvas — small glyph above each agent keyed to `agent.state`.
5. Hover tooltip on canvas — name, state, mini-bars for needs, cargo readout.
6. Decision-reason readout in `AgentPanel` — the engine's own explanation of why the current action was picked.
7. Backend-owned decision reason via a `Decision` dataclass returned from `decide_action`.

## Out of scope (deferred)

- Tool-swing animation variants (`Pawn_Interact_Hammer/Axe/Pickaxe/Knife`).
- Particle FX (Dust, Splash, Fire, Explosion).
- Trait aura / rogue-loner visualization on canvas (already shown as panel badge).
- Path overlay for selected agent.
- Death / spawn animations.
- New stats beyond the existing `hunger / energy / social / health / cargo`.

## Architecture

### Single-source-of-truth for action + reason

Replaces the previously-proposed parallel `decide_action()` + `reason_for()` pair, per `CLAUDE.md §Design principles`. One function, one ladder walk, structured return.

```python
# backend/app/engine/agent.py
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class Decision:
    action: str   # 'rest' | 'forage' | 'plant' | 'harvest' | 'socialise' |
                  # 'explore' | 'eat_camp' | 'eat_cargo' | 'deposit' |
                  # 'step_to_camp' | 'rest_outdoors'
    reason: str   # Human-readable branch explanation, e.g. 'hunger < 50 → forage'


def decide_action(agent, world, colony, phase) -> Decision:
    # One Decision(...) literal per branch. No parallel function walks
    # the same ladder — drift is impossible.
    if agent.health < needs.HEALTH_CRITICAL:
        if agent.energy < needs.ENERGY_CRITICAL:
            return Decision('rest',
                f'health < {int(needs.HEALTH_CRITICAL)} + '
                f'energy < {int(needs.ENERGY_CRITICAL)} → rest')
        return Decision('forage',
            f'health < {int(needs.HEALTH_CRITICAL)} → forage to recover')
    # ... 14 more branches, each returning Decision(action, reason) ...
```

All existing callers change from `action == 'rest'` to `decision.action == 'rest'`. Bulk rename.

Reason strings (all branches):

| Branch condition | Decision |
|------------------|----------|
| `health < HEALTH_CRITICAL` and `energy < ENERGY_CRITICAL` | `('rest', 'health < 20 + energy < 15 → rest')` |
| `health < HEALTH_CRITICAL` (energy ok) | `('forage', 'health < 20 → forage to recover')` |
| `hunger < HUNGER_CRITICAL` | `('forage', 'hunger < 20 → forage now')` |
| `energy < ENERGY_CRITICAL` (hunger ok) | `('rest', 'energy < 15 → rest')` |
| `phase == 'night'` | `('rest_outdoors', 'night phase → rest in place')` |
| `at_camp` + `cargo > 0` | `('deposit', 'at camp + cargo {N} → deposit')` |
| `at_camp` + `phase == 'dawn'` + hungry + stock + not already ate | `('eat_camp', 'dawn at camp → eat stock')` |
| `at_camp` + `social < SOCIAL_LOW` | `('socialise', 'at camp + social < 30 → socialise')` |
| `not rogue` + `social < SOCIAL_LOW` | `('step_to_camp', 'social < 30 → head to camp')` |
| `not rogue` + `cargo >= CARRY_MAX` | `('step_to_camp', 'cargo full → head to camp')` |
| `tile.crop_state == 'mature'` | `('harvest', 'mature crop → harvest')` |
| `tile.crop_state == 'none'` + empty + field room | `('plant', 'empty tile → plant')` |
| `rogue` + `cargo > 0` + `hunger < HUNGER_MODERATE` | `('eat_cargo', 'rogue + hunger < 50 → eat from pouch')` |
| `hunger < HUNGER_MODERATE` (tail) | `('forage', 'hunger < 50 → forage')` |
| default | `('explore', 'all needs ok → explore')` |

Thresholds are formatted as `int(needs.X)` in reason strings so the numbers update automatically if the constants change.

### `Agent.last_decision_reason`

Added to `Agent.__slots__`, initialized to `''` in `__init__`. Set in `tick_agent` right after the decision:

```python
decision = decide_action(agent, world, colony, phase)
agent.last_decision_reason = decision.reason
events.append(execute_action(decision.action, agent, world, all_agents, colony, rng=rng))
```

Not persisted to DB — it's derivable state, regenerated every tick. Lives only in-memory on the engine Agent + in the API response.

### API change

`agent_to_dict` in `backend/app/routes/serializers.py` gains one field:

```python
'decision_reason': agent.last_decision_reason,
```

Frontend type `Agent` in `frontend/src/api/types.ts` gains `decision_reason: string;`.

No new routes. No migrations. One serializer addition.

### Frontend file map

| File | Change |
|------|--------|
| `frontend/src/render/spriteAtlas.ts` | Load 4 colors × 4 anim variants = 16 pawn sheets (1536×192 each). Structure: `atlas.pawns: Record<ColonyColor, Record<AnimVariant, HTMLImageElement>>`. Existing `atlas.pawn` field deprecated but kept as fallback (points at Blue idle). |
| `frontend/src/render/animConfig.ts` *(new)* | Constants: `FRAME_MS = 100`, `FRAMES_PER_CYCLE = 8`, `MOVING_STATES: Set<AgentState>`, `STATE_ICON_MAP: Record<AgentState, string>`. |
| `frontend/src/render/Canvas2DRenderer.ts` | Per-agent anim state map `Map<agentId, AnimState>`, created lazily; advance per RAF by `dt`; switch variant on state/cargo change (resets frame to 0). Draw selected frame from correct sheet. `_drawStateIcon(ctx, agent)` helper. |
| `frontend/src/components/WorldCanvas.tsx` | `onPointerMove` handler (non-drag, throttled via ref timestamp); pixel-to-tile-to-agent lookup; local `useState<HoverState \| null>` for tooltip; clear on `pointerleave` and `pointerdown`. |
| `frontend/src/components/AgentTooltip.tsx` *(new)* | `position: fixed` div, viewport-clamped, renders name / colored colony pill / state icon + label / mini-bars / cargo line. |
| `frontend/src/components/AgentPanel.tsx` | Replace bare state pill with state pill + `<div className="decision-reason">{agent.decision_reason}</div>`. Hide reason line when empty string. |
| `frontend/src/api/types.ts` | `Agent.decision_reason: string`. |
| `frontend/src/styles.css` | `.agent-tooltip { … }`, `.decision-reason { … }`. |

Zero Zustand additions — hover state is ephemeral, lives in the canvas component only.

## Animation system

### Variants and sheets

```
assets/tiny-swords/free/Units/<Color> Units/Pawn/
  Pawn_Idle.png          → variant 'idle'
  Pawn_Run.png           → variant 'run'
  Pawn_Idle_Meat.png     → variant 'idleMeat'
  Pawn_Run_Meat.png      → variant 'runMeat'
```

Four colors × four variants = 16 sheets, each 1536×192 (8 frames of 192×192). Parallel load via existing `Promise.all`.

### Variant selector

```ts
type AnimVariant = 'idle' | 'run' | 'idleMeat' | 'runMeat';
const MOVING_STATES = new Set(['foraging', 'exploring', 'traversing', 'moving']);

function pickVariant(agent: Agent): AnimVariant {
  const moving = MOVING_STATES.has(agent.state);
  const carrying = agent.cargo > 0;
  if (moving && carrying) return 'runMeat';
  if (moving) return 'run';
  if (carrying) return 'idleMeat';
  return 'idle';
}
```

"Moving" is interpreted loosely — an agent mid-`forage` action often registers as `STATE_FORAGING` (still), but `STATE_TRAVERSING` (terrain cost mid-crossing) and `STATE_EXPLORING` are the ones that visually advance. The exact state-name mapping will be pinned during implementation by inspecting `backend/app/engine/actions.py` STATE_* constants.

### Frame cycling

```ts
interface AnimState {
  variant: AnimVariant;
  frameIndex: number;      // 0..7
  elapsedMs: number;       // time accumulator within the current frame
}

// Per RAF tick, dt = now - lastRafTime:
for (const [agentId, anim] of animStates) {
  anim.elapsedMs += dt;
  if (anim.elapsedMs >= FRAME_MS) {
    anim.frameIndex = (anim.frameIndex + 1) % FRAMES_PER_CYCLE;
    anim.elapsedMs -= FRAME_MS;
  }
}
```

When an agent's variant changes (state or cargo threshold crossed), reset `frameIndex = 0, elapsedMs = 0` so the new animation starts at its first frame instead of mid-cycle.

### Color resolver

`colony.name` already matches the palette (`DEFAULT_COLONY_PALETTE` in `backend/app/services/simulation_service.py` — Red / Blue / Purple / Yellow). Lookup: `atlas.pawns[colony.name]`. If agent's colony is the synthesized default (name `'_default'`, id `None`) — introduced in the Round D legacy-retirement cleanup — fall back to Blue pawn sheets.

## HUD additions

### State icon overlay

Rendered at `(agent_center_x, agent_y - 18px)` above the sprite, after the sprite draw, before the selection ring. 16-20px canvas text glyph.

```ts
const STATE_ICON_MAP: Record<AgentState, string> = {
  idle: '',             // no glyph when truly idle
  resting: '💤',
  foraging: '🌾',
  planting: '🌱',
  harvesting: '🌾',
  socialising: '💬',
  eating: '🍖',
  exploring: '·',
  traversing: '…',
  dead: '☠',
};
```

Opacity: 100% during day/dawn/dusk, 40% at night to avoid clutter during the sleep phase.

**Fallback:** If emoji render as box glyphs on the demo machine, swap to Tiny Swords UI icons (`assets/tiny-swords/free/UI Elements/UI Elements/Icons/Icon_*.png`) with a glyph→icon map. Deferred until flagged — adds ~12 extra sheet imports.

### Hover tooltip

```tsx
<div className="agent-tooltip" style={{ left: screenX + 8, top: screenY + 8 }}>
  <div className="agent-tooltip__head">
    {agent.name}
    <span className="pill" style={{ background: colony.color }}>{colony.name}</span>
  </div>
  <div className="agent-tooltip__state">
    {STATE_ICON_MAP[agent.state]} {agent.state}
  </div>
  <div className="agent-tooltip__bars">
    <MiniBar label="hunger" value={agent.hunger} />
    <MiniBar label="energy" value={agent.energy} />
    <MiniBar label="social" value={agent.social} />
    <MiniBar label="health" value={agent.health} />
  </div>
  {agent.cargo > 0 && <div className="agent-tooltip__cargo">cargo {agent.cargo.toFixed(1)} / {CARRY_MAX}</div>}
</div>
```

`MiniBar` is a 4-6 char unicode block-char bar (`█████░░░`) or a tiny styled div — decide during implementation.

**Lifecycle:**

- `WorldCanvas.tsx` listens for `pointermove` (non-drag) and throttles updates via ref timestamp (max 60 fps).
- Pixel → tile conversion reuses the existing click-handler math (extract into `pixelToTile()` helper).
- Tile → agent: `snapRef.current.agents.find(a => a.x === tileX && a.y === tileY && a.alive)`. O(n) is fine at demo scale (<100 agents).
- Clears on `pointerleave` (cursor exits canvas) and on `pointerdown` (drag-start takes priority).
- While drag is active (`dragRef.current` set), tooltip is suppressed.

Viewport clamp: if `screenX + tooltipWidth > window.innerWidth`, render to the left of the cursor instead of right.

### Decision-reason readout in `AgentPanel`

Above the existing needs meters, modify the `state` row:

```tsx
<dt>state</dt>
<dd>
  <span className={`pill ${agent.alive ? 'pill--alive' : 'pill--dead'}`}>
    {STATE_ICON_MAP[agent.state]} {agent.alive ? agent.state : 'deceased'}
  </span>
  {/* rogue/loner badges, unchanged */}
  {agent.decision_reason && (
    <div className="decision-reason">{agent.decision_reason}</div>
  )}
</dd>
```

Styling: 12px, muted color (`color: var(--text-muted)` or similar), no icon. Hides cleanly when `decision_reason === ''` (the empty-string initial state, before the first tick).

## Testing strategy

### Backend (pytest)

| Test file | Action |
|-----------|--------|
| `backend/tests/engine/test_agent.py` | Bulk rename: `decide_action(...) == 'rest'` → `decide_action(...).action == 'rest'`. ~11 call sites. Still 22 tests. |
| `backend/tests/engine/test_decide_action_phase.py` | Same bulk rename. ~9 sites. |
| `backend/tests/engine/test_decision_reason.py` *(new)* | 15 tests — one per `Decision` branch. Each asserts `decision.action == expected_action` AND `decision.reason == expected_reason`. |
| `backend/tests/engine/test_tick_agent.py` *(new, or add to test_agent.py)* | 1 test: after `tick_agent(...)`, `agent.last_decision_reason` is non-empty and matches what `decide_action(...).reason` would return for the same state. |
| `backend/tests/services/test_simulation_service.py` | 1 test: response from `get_current_simulation()`-derived serializer includes `decision_reason` key for every agent dict. |

### Frontend (vitest + tsc)

| Test file | Action |
|-----------|--------|
| `frontend/src/render/spriteAtlas.test.ts` *(new)* | Atlas load returns all 4 colors × 4 variants. Unknown colony color falls back to Blue. |
| `frontend/src/render/Canvas2DRenderer.test.ts` | Add: frame cycler advances `frameIndex` at 10 fps; `pickVariant` returns `runMeat` when moving + cargo > 0; state icon drawn at correct offset. |
| `frontend/src/components/AgentTooltip.test.tsx` *(new)* | Renders name/state/needs; clamps to left side when right-edge overflow; hides when `agent` prop is null. |
| `frontend/src/components/AgentPanel.test.tsx` | Add: decision_reason line renders below state pill when non-empty; hidden when empty. |

No frontend test needed for the reason *text* itself — backend owns the strings. Frontend only asserts the line renders.

### Manual test plan (5 min, pre-commit)

1. `docker compose up`, create 4-colony sim (4 colonies × 3 agents), play.
2. Visually confirm: Red colony pawns are red-tinted, Blue blue, Purple purple, Yellow yellow.
3. Watch for ~30 ticks: moving pawns play Run cycle; idle pawns play Idle cycle.
4. Let an agent forage until cargo > 0 — sprite swaps to `_Meat` variant (visibly carrying meat).
5. Hover over a pawn → tooltip appears within ~100 ms showing name, state, bars.
6. Click the pawn → `AgentPanel` opens with state pill + reason line below.
7. Let sim run past tick 120 (through night) — reasons update; night-phase pawns show `'night phase → rest in place'`.
8. Run pytest + vitest + `tsc --noEmit` — all green.

## Risks

| Risk | Mitigation |
|------|------------|
| 16 new sprite sheets inflate bundle (~300-600 KB) | Demo-only environment, no prod first-paint concern; document size delta in commit. |
| Emoji glyphs render as boxes on some OSes | Fall back to Tiny Swords UI icons (Icon_*.png) if screencap shows ugly output. Scoped as a separate sub-task. |
| Tooltip fights with drag gesture | Clear tooltip on `pointerdown`; suppress entirely while `dragRef.current` is non-null. |
| Decision reason string changes break frontend tests | Frontend asserts only that the reason line renders (non-empty), not on exact text. |
| Per-agent anim state map grows unbounded as agents die/spawn | Sweep the map at end of each RAF: delete entries whose `agentId` isn't in the current snapshot. |
| `Decision` dataclass import at runtime | `dataclasses` is stdlib; no dependency added. Existing code paths unchanged beyond return-type. |

## Open questions

1. **State names.** The engine currently uses `STATE_IDLE`, `STATE_RESTING`, `STATE_FORAGING`, `STATE_EXPLORING`, `STATE_PLANTING`, `STATE_HARVESTING`, `STATE_SOCIALISING`, `STATE_EATING`, `STATE_DEAD`, `STATE_TRAVERSING` — the `STATE_ICON_MAP` above mirrors these. Implementation-time check: grep `backend/app/engine/actions.py` for the definitive list.
2. **Idle-vs-resting distinction for icon.** Both are "not moving" but the current code uses both state strings. Do we show 💤 for both, or only `resting`? Lean: only `resting`, let `idle` show no icon (common default case).
3. **Colony color fallback in practice.** The Round D synthesized default colony uses `name='_default'`. Is that string guaranteed to never collide with a user-defined colony name? (Current: yes, since demo uses `DEFAULT_COLONY_PALETTE` names only.) Decide at implementation: lock `'_default'` as a reserved sentinel or use `colony.id is None` as the fallback check.

## Implementation sequencing (expectation)

The writing-plans skill will decompose this into a task-by-task plan. Rough shape (subject to refinement):

1. Backend: `Decision` dataclass + `decide_action` refactor (all branches) + reason strings.
2. Backend: `Agent.last_decision_reason` slot + `tick_agent` integration + serializer field.
3. Backend: tests (per-branch reason test, tick_agent set test, serializer field test).
4. Frontend: type update + sprite atlas expansion + per-color resolver.
5. Frontend: animation state + frame cycling + variant picker.
6. Frontend: state icon overlay.
7. Frontend: hover tooltip + `AgentTooltip` component + pointer handlers.
8. Frontend: `AgentPanel` decision-reason readout.
9. Manual test + demo-ready commit.

Baseline to preserve: 227 backend + 36 frontend green at every step. New tests raise the counts — final baseline TBD by plan.
