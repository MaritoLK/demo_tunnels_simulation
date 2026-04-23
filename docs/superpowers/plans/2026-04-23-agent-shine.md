# Agent Shine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface engine depth per agent: animation cycling, per-colony pawn color, cargo-aware sprites, state-icon overlay, hover tooltip, and backend-owned decision reason — all without demo-breaking risk.

**Architecture:** Backend refactors `decide_action` to return a `Decision` dataclass (single source of truth for action + reason), stores `last_decision_reason` on each engine `Agent`, and adds a `sprite_palette` field on `Colony` that decouples sprite selection from display name. Frontend loads 16 pawn sheets (4 colors × 4 variants), cycles 8-frame animations keyed by position-delta motion detection (not state-string), renders a state icon overlay above each agent, and adds a hover tooltip (with decision-reason) plus a panel decision-reason line.

**Tech Stack:** Python 3.12, Flask-SQLAlchemy 3.1.1, Alembic, PostgreSQL 18, React 18, TypeScript, Vite, Vitest, Canvas 2D.

**Spec:** `docs/superpowers/specs/2026-04-23-agent-shine-design.md` (commits 18564ad, f4e60c2, 787e974).

**Baseline:** 227 backend tests + 36 frontend tests must stay green at every commit. The manual test in Task 18 is the final gate.

---

## File Structure

**Backend — modified:**
- `backend/app/engine/agent.py` — add `Decision` dataclass, refactor `decide_action` to return it, add `last_decision_reason` to `Agent.__slots__`, set it in `tick_agent`.
- `backend/app/engine/colony.py` — add `sprite_palette` to `EngineColony.__slots__` + `__init__`.
- `backend/app/engine/simulation.py` — synthesized default colony gets `sprite_palette='Blue'`.
- `backend/app/models/colony.py` — add `sprite_palette` column.
- `backend/app/services/simulation_service.py` — extend `DEFAULT_COLONY_PALETTE` to 3-tuples; thread `sprite_palette` through `_build_default_colonies`.
- `backend/app/services/mappers.py` — `colony_to_row`, `row_to_colony`, `update_colony_row` thread `sprite_palette`.
- `backend/app/routes/serializers.py` — `agent_to_dict` adds `decision_reason`; `colony_to_dict` adds `sprite_palette`.

**Backend — created:**
- `backend/migrations/versions/a0b1c2d3e4f5_colony_sprite_palette.py` — column add + backfill.
- `backend/tests/engine/test_decision_reason.py` — 15 per-branch tests.

**Backend — modified tests:**
- `backend/tests/engine/test_agent.py` — migrate 11 `decide_action(...) == str` to `decide_action(...).action == str`.
- `backend/tests/engine/test_decide_action_phase.py` — migrate 9 callers the same way.
- `backend/tests/services/test_mappers.py` — round-trip test for colony sprite_palette.
- `backend/tests/services/test_simulation_service.py` — assert serialized agent has `decision_reason` key.

**Frontend — modified:**
- `frontend/src/api/types.ts` — `Agent.decision_reason: string`; `Colony.sprite_palette: string`.
- `frontend/src/render/spriteAtlas.ts` — 16 pawn sheets, new `atlas.pawns` shape.
- `frontend/src/render/Canvas2DRenderer.ts` — per-agent anim state map, frame cycler, variant picker, palette-aware sheet selection, state icon overlay.
- `frontend/src/components/WorldCanvas.tsx` — pointermove hover handler, hover state.
- `frontend/src/components/AgentPanel.tsx` — decision-reason line below state pill.
- `frontend/src/styles.css` — `.agent-tooltip`, `.decision-reason`.

**Frontend — created:**
- `frontend/src/render/animConfig.ts` — `FRAME_MS`, `FRAMES_PER_CYCLE`, `STATE_ICON_MAP`.
- `frontend/src/components/AgentTooltip.tsx` — hover tooltip component.
- `frontend/src/components/AgentTooltip.test.tsx` — tooltip unit tests.
- `frontend/src/render/spriteAtlas.test.ts` — atlas shape + fallback tests.

---

## Test Commands

Backend (from repo root, **all tests run inside the `flask` container**; host pytest has no DB + wrong Python path):
```bash
docker compose run --rm flask pytest -q                     # full backend suite
docker compose run --rm flask pytest tests/engine/test_agent.py -v
docker compose run --rm flask flask db upgrade              # apply migrations
```

Frontend (from `frontend/`):
```bash
npm test                                                    # vitest (all files)
npx vitest run src/components/AgentTooltip.test.tsx         # single file
npx tsc --noEmit                                            # typecheck
```

---

## Invariants (enforce every task)

- **Baseline stays green.** 227 backend + 36 frontend must pass at every commit. New tests raise the counts; never lower.
- **Golden rule (CLAUDE.md):** "No green run = no claim." Paste `passed in X` output in commit message or task notes before marking done.
- **Decision single-source.** Never introduce a function that parallels `decide_action`'s ladder — reasons live in the `Decision` literal or don't exist.
- **sprite_palette decoupling.** Never look up a pawn sheet by `colony.name` — use `colony.sprite_palette`.
- **Migrations land with their mapper in the same commit.** Schema drift between commits breaks `rows_to_world` + friends silently.

---

## Phase A — Decision plumbing

### Task 1: Decision dataclass

**Files:**
- Modify: `backend/app/engine/agent.py` (top of file, after imports)
- Test: `backend/tests/engine/test_decision.py` (new)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/engine/test_decision.py`:
```python
"""Decision is a frozen, slotted dataclass with action + reason fields.
These tests lock the shape — callers will rely on both attributes existing."""
import pytest

from app.engine.agent import Decision


def test_decision_has_action_and_reason():
    d = Decision('rest', 'health < 20, energy < 15 → rest')
    assert d.action == 'rest'
    assert d.reason == 'health < 20, energy < 15 → rest'


def test_decision_is_frozen():
    from dataclasses import FrozenInstanceError
    d = Decision('rest', 'r')
    with pytest.raises(FrozenInstanceError):
        d.action = 'forage'


def test_decision_uses_slots():
    d = Decision('rest', 'r')
    # frozen=True + slots=True on CPython 3.11+ raises TypeError from
    # super().__setattr__, not AttributeError. Accept either.
    with pytest.raises((AttributeError, TypeError)):
        d.extra = 'whatever'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose run --rm flask pytest tests/engine/test_decision.py -v`
Expected: FAIL with `ImportError: cannot import name 'Decision' from 'app.engine.agent'`.

- [ ] **Step 3: Add Decision dataclass**

In `backend/app/engine/agent.py`, add to the top (after existing imports, before `class Agent`):
```python
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Decision:
    """Result of a decision tick. `action` is the action-name the engine
    picked; `reason` is a short human-readable explanation of which
    branch of the priority ladder fired. Both come from one ladder walk
    inside decide_action — never from two parallel functions."""
    action: str
    reason: str
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose run --rm flask pytest tests/engine/test_decision.py -v`
Expected: 3 passed.

- [ ] **Step 5: Run full backend suite to confirm no regression**

Run: `docker compose run --rm flask pytest -q`
Expected: 230 passed (227 baseline + 3 new).

- [ ] **Step 6: Commit**

```bash
git add backend/app/engine/agent.py backend/tests/engine/test_decision.py
git commit -m "$(cat <<'EOF'
feat(engine): add Decision dataclass (frozen + slots)

Single-source-of-truth type for decide_action's return value —
action + reason from one ladder walk. Next commit refactors
decide_action to return it.

Refs docs/superpowers/specs/2026-04-23-agent-shine-design.md
EOF
)"
```

---

### Task 2: decide_action returns Decision (big-bang refactor + caller migration)

**Files:**
- Modify: `backend/app/engine/agent.py` — `decide_action` body (all 15 branches), `tick_agent` call site.
- Modify: `backend/tests/engine/test_agent.py` — 11 call sites: `== 'rest'` → `.action == 'rest'`.
- Modify: `backend/tests/engine/test_decide_action_phase.py` — 9 call sites: same rewrite.

This task is one atomic commit because changing the return type breaks all callers simultaneously.

- [ ] **Step 1: Refactor `decide_action` to return Decision**

In `backend/app/engine/agent.py`, replace the entire `decide_action` function body (lines 57-147 in the current file, roughly — use `grep -n "def decide_action" backend/app/engine/agent.py` to confirm). Replace with:

```python
def decide_action(agent, world, colony, phase) -> Decision:
    """Return the Decision (action-name + reason) for this agent this tick.

    Priority ladder (first match wins):
      1. Survival (health / hunger / energy crits).
      2. Night → rest_outdoors in place.
      3. At-camp opportunistic (deposit / eat / socialise).
      4. Social-low off-camp → step_to_camp.
      5. Cargo-full off-camp → step_to_camp.
      6. Tile-local (harvest / plant).
      7. Rogue eat-from-pouch.
      8. Tail (forage / explore).

    Every branch returns one Decision literal so action + reason cannot
    drift. See CLAUDE.md §Design principles.
    """
    hc = int(needs.HEALTH_CRITICAL)
    ec = int(needs.ENERGY_CRITICAL)
    hu_c = int(needs.HUNGER_CRITICAL)
    hu_m = int(needs.HUNGER_MODERATE)
    sl = int(needs.SOCIAL_LOW)

    # 1. Survival
    if agent.health < needs.HEALTH_CRITICAL:
        if agent.energy < needs.ENERGY_CRITICAL:
            return Decision('rest', f'health < {hc}, energy < {ec} → rest')
        return Decision('forage', f'health < {hc} → forage to recover')
    if agent.hunger < needs.HUNGER_CRITICAL:
        return Decision('forage', f'hunger < {hu_c} → forage now')
    if agent.energy < needs.ENERGY_CRITICAL:
        return Decision('rest', f'energy < {ec} → rest')

    at_camp = colony.is_at_camp(agent.x, agent.y) if not agent.rogue else False

    # 2. Night
    if phase == 'night':
        return Decision('rest_outdoors', 'night phase → rest in place')

    # 3. At-camp opportunistic
    if at_camp:
        if agent.cargo > 0:
            return Decision('deposit', f'at camp, cargo {agent.cargo:.1f} → deposit')
        if (phase == 'dawn'
                and agent.hunger < needs.NEED_MAX
                and colony.food_stock >= config.EAT_COST
                and not agent.ate_this_dawn):
            return Decision('eat_camp', 'dawn at camp → eat stock')
        if agent.social < needs.SOCIAL_LOW:
            return Decision('socialise', f'at camp, social < {sl} → socialise')

    # 4. Social-low off-camp
    if not agent.rogue and agent.social < needs.SOCIAL_LOW:
        return Decision('step_to_camp', f'social < {sl} → head to camp')

    # 5. Cargo-full off-camp
    if not agent.rogue and agent.cargo >= needs.CARRY_MAX:
        return Decision('step_to_camp', 'cargo full → head to camp')

    # 6. Tile-local
    tile = world.get_tile(agent.x, agent.y)
    if tile.crop_state == 'mature':
        return Decision('harvest', 'mature crop → harvest')
    if (tile.crop_state == 'none'
            and tile.resource_amount == 0
            and colony.growing_count < config.MAX_FIELDS_PER_COLONY):
        return Decision('plant', 'empty tile → plant')

    # 7. Rogue eat-from-pouch
    if agent.rogue and agent.cargo > 0 and agent.hunger < needs.HUNGER_MODERATE:
        return Decision('eat_cargo', f'rogue, hunger < {hu_m} → eat from pouch')

    # 8. Tail
    if agent.hunger < needs.HUNGER_MODERATE:
        return Decision('forage', f'hunger < {hu_m} → forage')
    return Decision('explore', 'all needs ok → explore')
```

- [ ] **Step 2: Update `tick_agent` to extract `.action`**

In `backend/app/engine/agent.py`, find the `tick_agent` function. The existing line reads (approximately):
```python
action_name = decide_action(agent, world, colony, phase)
events.append(execute_action(action_name, agent, world, all_agents, colony, rng=rng))
```

Replace with:
```python
decision = decide_action(agent, world, colony, phase)
events.append(execute_action(decision.action, agent, world, all_agents, colony, rng=rng))
```

(We'll add `agent.last_decision_reason = decision.reason` in Task 4.)

- [ ] **Step 3: Migrate `test_agent.py` callers**

In `backend/tests/engine/test_agent.py`, use sed or bulk edit to change every occurrence of `decide_action(...) == '<action>'` to `decide_action(...).action == '<action>'`. Verify with:

```bash
grep -n "decide_action(" backend/tests/engine/test_agent.py
```

Should show ~11 lines, each with `.action`. Example:

Before: `assert decide_action(a, _grass_world(), _colony(), 'day') == 'rest'`
After:  `assert decide_action(a, _grass_world(), _colony(), 'day').action == 'rest'`

- [ ] **Step 4: Migrate `test_decide_action_phase.py` callers**

Same rewrite in `backend/tests/engine/test_decide_action_phase.py`. ~9 sites. Verify:

```bash
grep -n "decide_action(" backend/tests/engine/test_decide_action_phase.py
```

Every matching line should end in `.action == '<string>'`.

- [ ] **Step 5: Run full backend suite**

Run: `docker compose run --rm flask pytest -q`
Expected: 230 passed (227 existing + 3 Decision tests; unchanged after the refactor because the behavior is preserved).

If any fail: the rewrite missed a call site — grep `decide_action(` across `backend/` and find the stragglers.

- [ ] **Step 6: Commit**

```bash
git add backend/app/engine/agent.py backend/tests/engine/test_agent.py backend/tests/engine/test_decide_action_phase.py
git commit -m "$(cat <<'EOF'
refactor(engine): decide_action returns Decision; migrate all callers

All 15 branches return Decision(action, reason) literals — action and
reason cannot drift. tick_agent extracts .action; existing test
assertions migrate to decide_action(...).action.

Refs docs/superpowers/specs/2026-04-23-agent-shine-design.md
EOF
)"
```

---

### Task 3: Per-branch decision reason tests

**Files:**
- Test: `backend/tests/engine/test_decision_reason.py` (new)

- [ ] **Step 1: Create the test file skeleton**

Create `backend/tests/engine/test_decision_reason.py`:
```python
"""Per-branch Decision tests. One per branch of decide_action's priority
ladder. Each asserts (a) .action == expected, and (b) a discriminator
substring is present in .reason. Substring assertions intentionally
don't lock exact wording — reason strings evolve; action + discriminator
is the load-bearing invariant.

See docs/superpowers/specs/2026-04-23-agent-shine-design.md §Single-
source-of-truth for action + reason.
"""
from app.engine import config, needs
from app.engine.agent import Agent, decide_action
from app.engine.colony import EngineColony
from app.engine.world import Tile, World


def _grass_world(w=5, h=5):
    world = World(w, h)
    world.tiles = [
        [Tile(x=x, y=y, terrain='grass', resource_type=None, resource_amount=0)
         for x in range(w)]
        for y in range(h)
    ]
    return world


def _off_camp_colony():
    """Camp off-grid so agents are never at_camp."""
    return EngineColony(id=1, name='Test', color='#000', camp_x=99, camp_y=99,
                        food_stock=18,
                        growing_count=config.MAX_FIELDS_PER_COLONY)


def _at_camp_colony():
    """Camp at (0,0) for at-camp branch tests."""
    return EngineColony(id=1, name='Test', color='#000', camp_x=0, camp_y=0,
                        food_stock=18,
                        growing_count=config.MAX_FIELDS_PER_COLONY)


def _healthy_agent(x=2, y=2, colony_id=1):
    a = Agent('X', x, y, colony_id=colony_id)
    a.hunger = needs.NEED_MAX
    a.energy = needs.NEED_MAX
    a.social = needs.NEED_MAX
    a.health = needs.NEED_MAX
    return a
```

- [ ] **Step 2: Add survival-branch tests**

Append to `test_decision_reason.py`:
```python
def test_critical_health_low_energy_picks_rest_with_health_and_energy_reason():
    a = _healthy_agent()
    a.health = needs.HEALTH_CRITICAL - 1
    a.energy = needs.ENERGY_CRITICAL - 1
    d = decide_action(a, _grass_world(), _off_camp_colony(), 'day')
    assert d.action == 'rest'
    assert 'health' in d.reason
    assert 'energy' in d.reason


def test_critical_health_high_energy_picks_forage_with_health_reason():
    a = _healthy_agent()
    a.health = needs.HEALTH_CRITICAL - 1
    d = decide_action(a, _grass_world(), _off_camp_colony(), 'day')
    assert d.action == 'forage'
    assert 'health' in d.reason


def test_critical_hunger_picks_forage_with_hunger_reason():
    a = _healthy_agent()
    a.hunger = needs.HUNGER_CRITICAL - 1
    d = decide_action(a, _grass_world(), _off_camp_colony(), 'day')
    assert d.action == 'forage'
    assert 'hunger' in d.reason


def test_critical_energy_picks_rest_with_energy_reason():
    a = _healthy_agent()
    a.energy = needs.ENERGY_CRITICAL - 1
    d = decide_action(a, _grass_world(), _off_camp_colony(), 'day')
    assert d.action == 'rest'
    assert 'energy' in d.reason
```

- [ ] **Step 3: Add phase and at-camp branch tests**

Append:
```python
def test_night_phase_picks_rest_outdoors_with_night_reason():
    a = _healthy_agent()
    d = decide_action(a, _grass_world(), _off_camp_colony(), 'night')
    assert d.action == 'rest_outdoors'
    assert 'night' in d.reason


def test_at_camp_with_cargo_picks_deposit_with_cargo_reason():
    a = _healthy_agent(x=0, y=0)
    a.cargo = 3.0
    d = decide_action(a, _grass_world(), _at_camp_colony(), 'day')
    assert d.action == 'deposit'
    assert 'cargo' in d.reason


def test_at_camp_dawn_hungry_with_stock_picks_eat_camp():
    a = _healthy_agent(x=0, y=0)
    a.hunger = 60.0                # < NEED_MAX so eligible to eat
    a.ate_this_dawn = False
    d = decide_action(a, _grass_world(), _at_camp_colony(), 'dawn')
    assert d.action == 'eat_camp'
    assert 'eat' in d.reason


def test_at_camp_low_social_picks_socialise():
    a = _healthy_agent(x=0, y=0)
    a.social = needs.SOCIAL_LOW - 1
    d = decide_action(a, _grass_world(), _at_camp_colony(), 'day')
    assert d.action == 'socialise'
    assert 'social' in d.reason
```

- [ ] **Step 4: Add off-camp and tile-local branch tests**

Append:
```python
def test_off_camp_low_social_picks_step_to_camp():
    a = _healthy_agent()
    a.social = needs.SOCIAL_LOW - 1
    d = decide_action(a, _grass_world(), _off_camp_colony(), 'day')
    assert d.action == 'step_to_camp'
    assert 'social' in d.reason


def test_off_camp_cargo_full_picks_step_to_camp():
    a = _healthy_agent()
    a.cargo = needs.CARRY_MAX
    d = decide_action(a, _grass_world(), _off_camp_colony(), 'day')
    assert d.action == 'step_to_camp'
    assert 'cargo' in d.reason


def test_mature_tile_picks_harvest():
    a = _healthy_agent()
    w = _grass_world()
    w.get_tile(a.x, a.y).crop_state = 'mature'
    d = decide_action(a, w, _off_camp_colony(), 'day')
    assert d.action == 'harvest'
    assert 'harvest' in d.reason or 'mature' in d.reason


def test_empty_tile_with_field_room_picks_plant():
    a = _healthy_agent()
    # off-camp colony uses growing_count=MAX. Override for this test:
    c = EngineColony(id=1, name='Test', color='#000', camp_x=99, camp_y=99,
                     food_stock=18, growing_count=0)
    d = decide_action(a, _grass_world(), c, 'day')
    assert d.action == 'plant'
    assert 'plant' in d.reason or 'empty' in d.reason
```

- [ ] **Step 5: Add rogue and tail branch tests**

Append:
```python
def test_rogue_hungry_with_cargo_picks_eat_cargo():
    a = _healthy_agent()
    a.rogue = True
    a.cargo = 2.0
    a.hunger = needs.HUNGER_MODERATE - 1
    d = decide_action(a, _grass_world(), _off_camp_colony(), 'day')
    assert d.action == 'eat_cargo'
    assert 'rogue' in d.reason or 'pouch' in d.reason


def test_tail_moderate_hunger_picks_forage():
    a = _healthy_agent()
    a.hunger = needs.HUNGER_MODERATE - 1
    d = decide_action(a, _grass_world(), _off_camp_colony(), 'day')
    assert d.action == 'forage'
    assert 'hunger' in d.reason


def test_tail_all_ok_picks_explore():
    a = _healthy_agent()
    d = decide_action(a, _grass_world(), _off_camp_colony(), 'day')
    assert d.action == 'explore'
    assert 'explore' in d.reason or 'ok' in d.reason
```

- [ ] **Step 6: Run the new test file**

Run: `docker compose run --rm flask pytest tests/engine/test_decision_reason.py -v`
Expected: 15 passed (5 survival/phase/at-camp + 4 at-camp/off-camp + 3 tile-local + 3 rogue/tail — count might vary ±1 if some cases merge; all must pass).

- [ ] **Step 7: Run full suite**

Run: `docker compose run --rm flask pytest -q`
Expected: 245 passed (230 + 15).

- [ ] **Step 8: Commit**

```bash
git add backend/tests/engine/test_decision_reason.py
git commit -m "$(cat <<'EOF'
test(engine): per-branch Decision tests with discriminator substrings

15 tests, one per decide_action branch. Each asserts action + key
substring in reason — never full-string equality. Wording can evolve
without cascading test churn; wrong-branch-fired still caught.
EOF
)"
```

---

### Task 4: Agent.last_decision_reason slot + tick_agent writes it

**Files:**
- Modify: `backend/app/engine/agent.py` — `Agent.__slots__`, `Agent.__init__`, `tick_agent`.
- Modify: `backend/tests/engine/test_agent.py` — add test that the field is set after a tick.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/engine/test_agent.py`:
```python
def test_tick_agent_sets_last_decision_reason():
    """After one tick, agent.last_decision_reason is populated with the
    same string decide_action returned. Empty string before the first
    tick is also a contract (Agent.__init__ default)."""
    world = _grass_world()
    a = Agent('Alice', 1, 1, colony_id=1)
    assert a.last_decision_reason == ''          # pre-tick default
    tick_agent(a, world, [a], {1: _colony()}, phase='day',
               rng=random.Random(0))
    assert a.last_decision_reason != ''          # now populated
    # Reason should mention at least one semantic token the engine uses
    assert any(token in a.last_decision_reason for token in
               ('hunger', 'energy', 'social', 'cargo', 'explore', 'plant', 'forage'))
```

- [ ] **Step 2: Run test — fails on `last_decision_reason == ''`**

Run: `docker compose run --rm flask pytest tests/engine/test_agent.py::test_tick_agent_sets_last_decision_reason -v`
Expected: FAIL with `AttributeError: 'Agent' object has no attribute 'last_decision_reason'` (the slot doesn't exist yet).

- [ ] **Step 3: Add slot + init**

In `backend/app/engine/agent.py`, modify `Agent.__slots__` (currently around line 6-14). Add `'last_decision_reason'` to the tuple:

```python
class Agent:
    __slots__ = (
        'id', 'name', 'x', 'y', 'state',
        'hunger', 'energy', 'social', 'health',
        'age', 'alive',
        'colony_id', 'ate_this_dawn',
        'move_cooldown',
        'rogue', 'loner',
        'cargo',
        'last_decision_reason',   # NEW
    )
```

In `Agent.__init__`, add the init (after `self.cargo = 0.0`, near the end of __init__):
```python
        # Populated per tick by tick_agent after decide_action. Empty string
        # before the first tick so serializer + UI can treat absence as
        # "no decision yet" without special-casing None.
        self.last_decision_reason = ''
```

- [ ] **Step 4: Update `tick_agent` to write the field**

In `tick_agent`, find the `decision = decide_action(...)` line added in Task 2. Add a set right after:
```python
        decision = decide_action(agent, world, colony, phase)
        agent.last_decision_reason = decision.reason
        events.append(execute_action(decision.action, agent, world, all_agents, colony, rng=rng))
```

- [ ] **Step 5: Run the new test**

Run: `docker compose run --rm flask pytest tests/engine/test_agent.py::test_tick_agent_sets_last_decision_reason -v`
Expected: 1 passed.

- [ ] **Step 6: Run full suite**

Run: `docker compose run --rm flask pytest -q`
Expected: 246 passed (245 + 1).

- [ ] **Step 7: Commit**

```bash
git add backend/app/engine/agent.py backend/tests/engine/test_agent.py
git commit -m "$(cat <<'EOF'
feat(engine): Agent.last_decision_reason slot + tick_agent writes it

New __slots__ entry, initialized to '' in __init__. Set by tick_agent
after decide_action so serializers / UI can surface the engine's own
explanation of why the current action was picked.
EOF
)"
```

---

### Task 5: agent_to_dict emits decision_reason + Agent type

**Files:**
- Modify: `backend/app/routes/serializers.py` — `agent_to_dict`.
- Modify: `frontend/src/api/types.ts` — add `Agent.decision_reason`.
- Test: add to existing `backend/tests/services/test_simulation_service.py` or `test_mappers.py`.

- [ ] **Step 1: Write the backend serializer test**

Append to `backend/tests/services/test_mappers.py` (or a similar existing test file — pick the one most related to serializers):
```python
def test_agent_to_dict_emits_decision_reason():
    """The wire shape must carry last_decision_reason under the
    decision_reason key. Frontend relies on this field being present
    on every serialized agent (empty string is fine pre-tick)."""
    from app.engine.agent import Agent
    from app.routes.serializers import agent_to_dict

    a = Agent('Alice', 1, 1)
    a.last_decision_reason = 'hunger < 50 → forage'
    dumped = agent_to_dict(a)
    assert 'decision_reason' in dumped
    assert dumped['decision_reason'] == 'hunger < 50 → forage'


def test_agent_to_dict_decision_reason_empty_pre_tick():
    from app.engine.agent import Agent
    from app.routes.serializers import agent_to_dict

    a = Agent('Bob', 2, 2)  # last_decision_reason defaults to ''
    dumped = agent_to_dict(a)
    assert dumped['decision_reason'] == ''
```

- [ ] **Step 2: Run test — fails on missing key**

Run: `docker compose run --rm flask pytest tests/services/test_mappers.py -k decision_reason -v`
Expected: FAIL (KeyError or `'decision_reason' not in ...`).

- [ ] **Step 3: Add field to `agent_to_dict`**

In `backend/app/routes/serializers.py`, find `agent_to_dict` (around line 14-33). Add one line before the closing brace:

```python
def agent_to_dict(agent):
    return {
        'id': agent.id,
        'name': agent.name,
        'x': agent.x,
        'y': agent.y,
        'state': agent.state,
        'hunger': agent.hunger,
        'energy': agent.energy,
        'social': agent.social,
        'health': agent.health,
        'age': agent.age,
        'alive': agent.alive,
        'colony_id': agent.colony_id,
        'rogue': agent.rogue,
        'loner': agent.loner,
        'cargo': agent.cargo,
        'decision_reason': agent.last_decision_reason,  # NEW
    }
```

- [ ] **Step 4: Run backend test — passes**

Run: `docker compose run --rm flask pytest tests/services/test_mappers.py -k decision_reason -v`
Expected: 2 passed.

- [ ] **Step 5: Update frontend Agent type**

In `frontend/src/api/types.ts`, modify the `Agent` interface (around line 27-53). Add a new field:

```typescript
export interface Agent {
  id: number;
  name: string;
  x: number;
  y: number;
  state: string;
  hunger: number;
  energy: number;
  social: number;
  health: number;
  age: number;
  alive: boolean;
  colony_id: number | null;
  rogue?: boolean;
  loner?: boolean;
  cargo?: number;
  // Engine's own one-line explanation of the last decide_action branch
  // that fired for this agent. Empty string before the first tick.
  decision_reason: string;   // NEW (non-optional — backend always sets)
}
```

- [ ] **Step 6: Verify frontend typecheck**

From `frontend/`:
```bash
npx tsc --noEmit
```
Expected: no errors (no frontend caller uses `decision_reason` yet, so the type add is non-breaking).

- [ ] **Step 7: Run both suites**

```bash
docker compose run --rm flask pytest -q          # expect 248
( cd frontend && npm test )                      # expect 36 still green
```

- [ ] **Step 8: Commit**

```bash
git add backend/app/routes/serializers.py backend/tests/services/test_mappers.py frontend/src/api/types.ts
git commit -m "$(cat <<'EOF'
feat(api): surface decision_reason on agent wire shape

Serializer emits the per-tick last_decision_reason as decision_reason.
Frontend Agent type updated; no callers yet — consumed by AgentPanel
and AgentTooltip in later tasks.
EOF
)"
```

---

## Phase B — Colony sprite_palette plumbing

### Task 6: Colony ORM field + migration

**Files:**
- Modify: `backend/app/models/colony.py` — add `sprite_palette` column.
- Create: `backend/migrations/versions/a0b1c2d3e4f5_colony_sprite_palette.py`.

- [ ] **Step 1: Peek at existing Colony model**

Run: `cat backend/app/models/colony.py`

Note the existing columns and table name. Typical shape (adjust to reality):
```python
class Colony(db.Model):
    __tablename__ = 'colonies'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    color = db.Column(db.String(7), nullable=False)
    camp_x = db.Column(db.Integer, nullable=False)
    camp_y = db.Column(db.Integer, nullable=False)
    food_stock = db.Column(db.Float, nullable=False, default=0.0, server_default='0.0')
```

- [ ] **Step 2: Add `sprite_palette` column**

Edit `backend/app/models/colony.py`. After the `food_stock` column (or wherever is alphabetical/convention-matching), add:

```python
    sprite_palette = db.Column(db.String(16), nullable=False,
                               default='Blue', server_default='Blue')
```

The `server_default='Blue'` is load-bearing — the migration's backfill depends on existing rows picking up this default before the explicit `UPDATE` runs.

- [ ] **Step 3: Generate the migration file**

Flask-Migrate's auto-gen may miss server_default. Write the migration manually. Create `backend/migrations/versions/a0b1c2d3e4f5_colony_sprite_palette.py`:

```python
"""colony sprite_palette column

Revision ID: a0b1c2d3e4f5
Revises: f7e8d9a0b1c2
Create Date: 2026-04-23

"""
from alembic import op
import sqlalchemy as sa


revision = 'a0b1c2d3e4f5'
down_revision = 'f7e8d9a0b1c2'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'colonies',
        sa.Column(
            'sprite_palette',
            sa.String(length=16),
            nullable=False,
            server_default='Blue',
        ),
    )
    # Explicit backfill for rows whose name matches the DEFAULT_COLONY_PALETTE.
    # Rows with any other name keep the 'Blue' server_default. No demo data
    # hits the else branch today; the explicit IN list prevents future
    # non-palette colonies from silently becoming Blue without notice.
    op.execute(
        "UPDATE colonies SET sprite_palette = name "
        "WHERE name IN ('Red', 'Blue', 'Purple', 'Yellow')"
    )


def downgrade():
    op.drop_column('colonies', 'sprite_palette')
```

**Important:** verify `down_revision = 'f7e8d9a0b1c2'` is actually the latest revision. Run:
```bash
ls backend/migrations/versions/ | sort
```
And confirm the last filename matches `f7e8d9a0b1c2_*`. If not, update `down_revision` accordingly.

- [ ] **Step 4: Apply the migration against the test DB**

Run: `docker compose run --rm flask flask db upgrade`
Expected: `Running upgrade f7e8d9a0b1c2 -> a0b1c2d3e4f5, colony sprite_palette column`.

- [ ] **Step 5: Run full suite to confirm the model + migration land cleanly**

Run: `docker compose run --rm flask pytest -q`
Expected: 248 passed. (Mapper still expects the old shape — that's Task 9. Baseline holds because existing tests don't serialize colonies through paths that read the new field yet.)

*If this step fails with errors about the colony row missing sprite_palette, it's because some test path reads the field before Task 9 threads it. Continue to Task 9 and come back — OR split this commit so the mapper change goes in the same commit. Pragmatic call by the implementer.*

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/colony.py backend/migrations/versions/a0b1c2d3e4f5_colony_sprite_palette.py
git commit -m "$(cat <<'EOF'
feat(models,migrations): add colony.sprite_palette column

Decouples agent sprite selection from colony.name. Server default 'Blue',
explicit backfill for names in the palette. Rows with non-palette names
keep 'Blue' by default — flagged in the migration comment.

Schema bump — run 'flask db upgrade' in dev.
EOF
)"
```

---

### Task 7: EngineColony sprite_palette + DEFAULT_COLONY_PALETTE extension

**Files:**
- Modify: `backend/app/engine/colony.py`.
- Modify: `backend/app/services/simulation_service.py` — `DEFAULT_COLONY_PALETTE` + `_build_default_colonies`.
- Modify: `backend/app/engine/simulation.py` — synthesized default colony.

- [ ] **Step 1: Write a failing engine-layer test**

Append to `backend/tests/services/test_mappers.py` (or add to `backend/tests/engine/test_simulation.py`):
```python
def test_default_simulation_colonies_have_sprite_palette():
    """4-colony default spawn: each colony has sprite_palette matching
    its name. Locks DEFAULT_COLONY_PALETTE → EngineColony threading."""
    from app.engine.simulation import new_simulation
    from app.engine.colony import EngineColony

    colonies = [
        EngineColony(id=i+1, name=name, color=color, camp_x=i, camp_y=i,
                     food_stock=10, sprite_palette=name)
        for i, (name, color) in enumerate(
            [('Red', '#e74c3c'), ('Blue', '#3498db')]
        )
    ]
    sim = new_simulation(10, 10, seed=42, colonies=colonies,
                         agents_per_colony=2)
    for c in sim.colonies.values():
        assert c.sprite_palette in ('Red', 'Blue')


def test_synthesized_default_colony_sprite_palette_is_blue():
    """Simulation.__init__ with colonies=None synthesizes a default.
    That default gets sprite_palette='Blue' so the frontend fallback
    is explicit at the data layer, not implicit in the renderer."""
    from app.engine.simulation import Simulation
    from app.engine.world import World

    w = World(3, 3)
    w.tiles = []  # generate() would populate; we just need the object
    for y in range(3):
        row = []
        for x in range(3):
            from app.engine.world import Tile
            row.append(Tile(x, y, 'grass'))
        w.tiles.append(row)

    sim = Simulation(w)                                      # no colonies
    default = next(iter(sim.colonies.values()))
    assert default.sprite_palette == 'Blue'
```

- [ ] **Step 2: Run test — fails on missing attribute**

Run: `docker compose run --rm flask pytest tests/services/test_mappers.py -k sprite_palette -v`
Expected: FAIL on `EngineColony() missing argument 'sprite_palette'` or `AttributeError`.

- [ ] **Step 3: Add slot + init to EngineColony**

In `backend/app/engine/colony.py`:
```python
class EngineColony:
    __slots__ = ('id', 'name', 'color', 'camp_x', 'camp_y',
                 'food_stock', 'growing_count', 'sprite_palette')

    def __init__(self, id, name, color, camp_x, camp_y,
                 food_stock, growing_count=0, sprite_palette='Blue'):
        self.id = id
        self.name = name
        self.color = color
        self.camp_x = camp_x
        self.camp_y = camp_y
        self.food_stock = food_stock
        self.growing_count = growing_count
        self.sprite_palette = sprite_palette

    def is_at_camp(self, x, y):
        return x == self.camp_x and y == self.camp_y

    def __repr__(self):
        return f"EngineColony(#{self.id} {self.name}/{self.sprite_palette} @({self.camp_x},{self.camp_y}))"
```

- [ ] **Step 4: Extend DEFAULT_COLONY_PALETTE and _build_default_colonies**

In `backend/app/services/simulation_service.py`, change `DEFAULT_COLONY_PALETTE` to 3-tuples:
```python
DEFAULT_COLONY_PALETTE = [
    ('Red',    '#e74c3c', 'Red'),
    ('Blue',   '#3498db', 'Blue'),
    ('Purple', '#9b59b6', 'Purple'),
    ('Yellow', '#f1c40f', 'Yellow'),
]
```

Update `_build_default_colonies` to pass `sprite_palette`:
```python
def _build_default_colonies(width, height, n_colonies):
    positions = _default_camp_positions(width, height, n_colonies)
    palette = DEFAULT_COLONY_PALETTE[:n_colonies]
    out = []
    for (name, color, sprite_palette), (cx, cy) in zip(palette, positions):
        out.append(EngineColony(
            id=None, name=name, color=color,
            camp_x=cx, camp_y=cy,
            food_stock=engine_config.INITIAL_FOOD_STOCK,
            sprite_palette=sprite_palette,
        ))
    return out
```

- [ ] **Step 5: Update synthesized default colony in Simulation.__init__**

In `backend/app/engine/simulation.py`, find the synthesized default (from Round D cleanup):
```python
            default = EngineColony(id=None, name='_default', color='#000',
                                   camp_x=0, camp_y=0,
                                   food_stock=config.INITIAL_FOOD_STOCK,
                                   growing_count=0)
```
Change to pass `sprite_palette='Blue'`:
```python
            default = EngineColony(id=None, name='_default', color='#000',
                                   camp_x=0, camp_y=0,
                                   food_stock=config.INITIAL_FOOD_STOCK,
                                   growing_count=0,
                                   sprite_palette='Blue')
```

- [ ] **Step 6: Run the new tests**

Run: `docker compose run --rm flask pytest tests/services/test_mappers.py -k sprite_palette -v`
Expected: 2 passed.

- [ ] **Step 7: Run full suite**

Run: `docker compose run --rm flask pytest -q`
Expected: 250 passed (248 + 2).

- [ ] **Step 8: Commit**

```bash
git add backend/app/engine/colony.py backend/app/services/simulation_service.py backend/app/engine/simulation.py backend/tests/services/test_mappers.py
git commit -m "$(cat <<'EOF'
feat(engine,services): EngineColony carries sprite_palette end-to-end

__slots__ extended, __init__ accepts sprite_palette (default 'Blue').
DEFAULT_COLONY_PALETTE extended to 3-tuples; _build_default_colonies
threads the value through. Simulation.__init__ synthesized default
carries sprite_palette='Blue' so the renderer's fallback is explicit
at the data layer.
EOF
)"
```

---

### Task 8: mapper round-trip + colony_to_dict emits sprite_palette + Colony type

**Files:**
- Modify: `backend/app/services/mappers.py` — `colony_to_row`, `row_to_colony`, `update_colony_row`.
- Modify: `backend/app/routes/serializers.py` — `colony_to_dict`.
- Modify: `frontend/src/api/types.ts` — `Colony.sprite_palette`.
- Test: `backend/tests/services/test_mappers.py` — round-trip.

- [ ] **Step 1: Write the mapper round-trip test**

Append to `backend/tests/services/test_mappers.py`:
```python
def test_colony_mapper_round_trip_preserves_sprite_palette():
    """EngineColony → row → EngineColony keeps sprite_palette intact."""
    from app.services import mappers
    from app.engine.colony import EngineColony
    from app import db, models

    c = EngineColony(id=None, name='Red', color='#e74c3c',
                     camp_x=3, camp_y=3, food_stock=18,
                     sprite_palette='Red')
    row = mappers.colony_to_row(c)
    db.session.add(row)
    db.session.flush()
    restored = mappers.row_to_colony(row)
    assert restored.sprite_palette == 'Red'
    assert restored.name == 'Red'


def test_colony_to_dict_emits_sprite_palette():
    from app.engine.colony import EngineColony
    from app.routes.serializers import colony_to_dict

    c = EngineColony(id=1, name='Purple', color='#9b59b6',
                     camp_x=0, camp_y=0, food_stock=10,
                     sprite_palette='Purple')
    dumped = colony_to_dict(c)
    assert dumped['sprite_palette'] == 'Purple'
```

- [ ] **Step 2: Run test — fails**

Run: `docker compose run --rm flask pytest tests/services/test_mappers.py -k "round_trip or colony_to_dict_emits" -v`
Expected: FAIL (mapper doesn't pass sprite_palette; serializer doesn't emit it).

- [ ] **Step 3: Update `colony_to_row`**

In `backend/app/services/mappers.py`, find `colony_to_row`. Add sprite_palette:

```python
def colony_to_row(colony):
    return models.Colony(
        id=colony.id,
        name=colony.name,
        color=colony.color,
        camp_x=colony.camp_x,
        camp_y=colony.camp_y,
        food_stock=colony.food_stock,
        sprite_palette=colony.sprite_palette,   # NEW
    )
```

- [ ] **Step 4: Update `row_to_colony`**

Same file. Find `row_to_colony`:

```python
def row_to_colony(row):
    return EngineColony(
        id=row.id,
        name=row.name,
        color=row.color,
        camp_x=row.camp_x,
        camp_y=row.camp_y,
        food_stock=row.food_stock,
        sprite_palette=row.sprite_palette,      # NEW
    )
```

- [ ] **Step 5: Update `update_colony_row` (if present)**

If `mappers.py` has `update_colony_row`, sprite_palette is normally immutable post-create — don't include it. But verify the function doesn't need it:
```bash
grep -A 10 "def update_colony_row" backend/app/services/mappers.py
```
If the function touches every other field, add `row.sprite_palette = engine_colony.sprite_palette` to be consistent; if it only updates deltas, skip.

- [ ] **Step 6: Update `colony_to_dict`**

In `backend/app/routes/serializers.py`, find `colony_to_dict`:

```python
def colony_to_dict(colony):
    return {
        'id': colony.id,
        'name': colony.name,
        'color': colony.color,
        'camp_x': colony.camp_x,
        'camp_y': colony.camp_y,
        'food_stock': colony.food_stock,
        'growing_count': colony.growing_count,
        'sprite_palette': colony.sprite_palette,   # NEW
    }
```

- [ ] **Step 7: Update frontend Colony type**

In `frontend/src/api/types.ts`:
```typescript
export interface Colony {
  id: number;
  name: string;
  color: string;
  camp_x: number;
  camp_y: number;
  food_stock: number;
  growing_count: number;
  sprite_palette: string;   // NEW — 'Red' | 'Blue' | 'Purple' | 'Yellow' (open union)
}
```

- [ ] **Step 8: Run mapper tests + full suite**

```bash
docker compose run --rm flask pytest tests/services/test_mappers.py -k "round_trip or emits" -v    # expect 2 passed
docker compose run --rm flask pytest -q                                                             # expect 252 passed
( cd frontend && npx tsc --noEmit )                                                                 # expect clean
```

- [ ] **Step 9: Commit**

```bash
git add backend/app/services/mappers.py backend/app/routes/serializers.py backend/tests/services/test_mappers.py frontend/src/api/types.ts
git commit -m "$(cat <<'EOF'
feat(mappers,api): thread colony.sprite_palette through mapper + wire

colony_to_row / row_to_colony round-trip the new field; colony_to_dict
emits it; frontend Colony type adds the field. End-to-end decoupling
from colony.name is now in place.
EOF
)"
```

---

## Phase C — Frontend types + atlas

### Task 9: Sprite atlas expansion (16 pawn sheets, new shape)

**Files:**
- Modify: `frontend/src/render/spriteAtlas.ts`.
- Create: `frontend/src/render/spriteAtlas.test.ts`.

- [ ] **Step 1: Write the atlas test file**

Create `frontend/src/render/spriteAtlas.test.ts`:
```typescript
import { describe, it, expect, vi } from 'vitest';

// Tests assume the test environment has the vi.mock('./spriteAtlas') in
// setup.ts active — we unmock here to exercise the real loader shape.
vi.unmock('./spriteAtlas');

import { loadSprites, PAWN_FRAME_PX } from './spriteAtlas';

describe('spriteAtlas shape', () => {
  it('exposes PAWN_FRAME_PX = 192', () => {
    expect(PAWN_FRAME_PX).toBe(192);
  });

  it('loads 4 colors × 4 variants under atlas.pawns', async () => {
    const atlas = await loadSprites();
    for (const color of ['Red', 'Blue', 'Purple', 'Yellow']) {
      for (const variant of ['idle', 'run', 'idleMeat', 'runMeat']) {
        expect(atlas.pawns[color][variant]).toBeDefined();
        expect(atlas.pawns[color][variant]).toBeInstanceOf(HTMLImageElement);
      }
    }
  });
});
```

- [ ] **Step 2: Run test — fails**

Run: `( cd frontend && npx vitest run src/render/spriteAtlas.test.ts )`
Expected: FAIL — `atlas.pawns[color]` undefined.

- [ ] **Step 3: Expand `spriteAtlas.ts`**

Replace the pawn import block + atlas shape in `frontend/src/render/spriteAtlas.ts`:

```typescript
// Pawn sheets — 4 colors × 4 variants = 16 sheets. Each 1536×192 = 8
// frames × 192px. Cargo-aware variants (Idle_Meat, Run_Meat) show the
// pawn carrying meat — visual feedback that cargo > 0.
const pawnSheetPaths = {
  Red: {
    idle:     '../assets/tiny-swords/free/Units/Red Units/Pawn/Pawn_Idle.png',
    run:      '../assets/tiny-swords/free/Units/Red Units/Pawn/Pawn_Run.png',
    idleMeat: '../assets/tiny-swords/free/Units/Red Units/Pawn/Pawn_Idle Meat.png',
    runMeat:  '../assets/tiny-swords/free/Units/Red Units/Pawn/Pawn_Run Meat.png',
  },
  Blue: {
    idle:     '../assets/tiny-swords/free/Units/Blue Units/Pawn/Pawn_Idle.png',
    run:      '../assets/tiny-swords/free/Units/Blue Units/Pawn/Pawn_Run.png',
    idleMeat: '../assets/tiny-swords/free/Units/Blue Units/Pawn/Pawn_Idle Meat.png',
    runMeat:  '../assets/tiny-swords/free/Units/Blue Units/Pawn/Pawn_Run Meat.png',
  },
  Purple: {
    idle:     '../assets/tiny-swords/free/Units/Purple Units/Pawn/Pawn_Idle.png',
    run:      '../assets/tiny-swords/free/Units/Purple Units/Pawn/Pawn_Run.png',
    idleMeat: '../assets/tiny-swords/free/Units/Purple Units/Pawn/Pawn_Idle Meat.png',
    runMeat:  '../assets/tiny-swords/free/Units/Purple Units/Pawn/Pawn_Run Meat.png',
  },
  Yellow: {
    idle:     '../assets/tiny-swords/free/Units/Yellow Units/Pawn/Pawn_Idle.png',
    run:      '../assets/tiny-swords/free/Units/Yellow Units/Pawn/Pawn_Run.png',
    idleMeat: '../assets/tiny-swords/free/Units/Yellow Units/Pawn/Pawn_Idle Meat.png',
    runMeat:  '../assets/tiny-swords/free/Units/Yellow Units/Pawn/Pawn_Run Meat.png',
  },
};
```

**Important:** Vite resolves URL imports at build time from string literals — the map form above won't work. Replace with explicit imports at the top of the file and build the map from the imported vars. See implementation hint in Step 4.

- [ ] **Step 4: Use explicit imports (Vite requirement)**

Replace the placeholder map with explicit imports at the top of `spriteAtlas.ts` (after existing imports, before `TERRAIN_TILE`). Delete the old `pawnIdleUrl` single-import:

```typescript
// 4 colors × 4 variants = 16 explicit imports (Vite needs static URL
// strings; can't build import paths at runtime).
import redIdleUrl      from '../assets/tiny-swords/free/Units/Red Units/Pawn/Pawn_Idle.png';
import redRunUrl       from '../assets/tiny-swords/free/Units/Red Units/Pawn/Pawn_Run.png';
import redIdleMeatUrl  from '../assets/tiny-swords/free/Units/Red Units/Pawn/Pawn_Idle Meat.png';
import redRunMeatUrl   from '../assets/tiny-swords/free/Units/Red Units/Pawn/Pawn_Run Meat.png';
import blueIdleUrl     from '../assets/tiny-swords/free/Units/Blue Units/Pawn/Pawn_Idle.png';
import blueRunUrl      from '../assets/tiny-swords/free/Units/Blue Units/Pawn/Pawn_Run.png';
import blueIdleMeatUrl from '../assets/tiny-swords/free/Units/Blue Units/Pawn/Pawn_Idle Meat.png';
import blueRunMeatUrl  from '../assets/tiny-swords/free/Units/Blue Units/Pawn/Pawn_Run Meat.png';
import purpleIdleUrl     from '../assets/tiny-swords/free/Units/Purple Units/Pawn/Pawn_Idle.png';
import purpleRunUrl      from '../assets/tiny-swords/free/Units/Purple Units/Pawn/Pawn_Run.png';
import purpleIdleMeatUrl from '../assets/tiny-swords/free/Units/Purple Units/Pawn/Pawn_Idle Meat.png';
import purpleRunMeatUrl  from '../assets/tiny-swords/free/Units/Purple Units/Pawn/Pawn_Run Meat.png';
import yellowIdleUrl     from '../assets/tiny-swords/free/Units/Yellow Units/Pawn/Pawn_Idle.png';
import yellowRunUrl      from '../assets/tiny-swords/free/Units/Yellow Units/Pawn/Pawn_Run.png';
import yellowIdleMeatUrl from '../assets/tiny-swords/free/Units/Yellow Units/Pawn/Pawn_Idle Meat.png';
import yellowRunMeatUrl  from '../assets/tiny-swords/free/Units/Yellow Units/Pawn/Pawn_Run Meat.png';
```

- [ ] **Step 5: Update `SpriteAtlas` interface and `loadSprites`**

Replace the `SpriteAtlas` interface:
```typescript
export type PawnVariant = 'idle' | 'run' | 'idleMeat' | 'runMeat';
export type ColonyPalette = 'Red' | 'Blue' | 'Purple' | 'Yellow';

export interface SpriteAtlas {
  tilemap: HTMLImageElement;
  water: HTMLImageElement;
  meat: HTMLImageElement;
  bush: HTMLImageElement;
  rock: HTMLImageElement;
  // Deprecated — the old single-pawn field. Keep for compatibility with
  // any render path that hasn't migrated to the per-palette lookup yet;
  // points at Blue idle so behavior is unchanged.
  pawn: HTMLImageElement;
  pawns: Record<ColonyPalette, Record<PawnVariant, HTMLImageElement>>;
  houses: Record<string, HTMLImageElement>;
}
```

Replace `loadSprites`:
```typescript
export async function loadSprites(): Promise<SpriteAtlas> {
  const loadPair = (urls: Record<PawnVariant, string>) =>
    Promise.all([
      loadImage(urls.idle),
      loadImage(urls.run),
      loadImage(urls.idleMeat),
      loadImage(urls.runMeat),
    ]);

  const [
    tilemap, water, meat, bush, rock,
    redPawns, bluePawns, purplePawns, yellowPawns,
    houseRed, houseBlue, housePurple, houseYellow,
  ] = await Promise.all([
    loadImage(tilemapUrl),
    loadImage(waterUrl),
    loadImage(meatUrl),
    loadImage(bushUrl),
    loadImage(rockUrl),
    loadPair({ idle: redIdleUrl,    run: redRunUrl,    idleMeat: redIdleMeatUrl,    runMeat: redRunMeatUrl }),
    loadPair({ idle: blueIdleUrl,   run: blueRunUrl,   idleMeat: blueIdleMeatUrl,   runMeat: blueRunMeatUrl }),
    loadPair({ idle: purpleIdleUrl, run: purpleRunUrl, idleMeat: purpleIdleMeatUrl, runMeat: purpleRunMeatUrl }),
    loadPair({ idle: yellowIdleUrl, run: yellowRunUrl, idleMeat: yellowIdleMeatUrl, runMeat: yellowRunMeatUrl }),
    loadImage(houseRedUrl),
    loadImage(houseBlueUrl),
    loadImage(housePurpleUrl),
    loadImage(houseYellowUrl),
  ]);

  const packPawns = (arr: HTMLImageElement[]): Record<PawnVariant, HTMLImageElement> => ({
    idle: arr[0], run: arr[1], idleMeat: arr[2], runMeat: arr[3],
  });

  return {
    tilemap, water, meat, bush, rock,
    pawn: bluePawns[0],   // legacy single-pawn field = Blue idle (unchanged behavior)
    pawns: {
      Red:    packPawns(redPawns),
      Blue:   packPawns(bluePawns),
      Purple: packPawns(purplePawns),
      Yellow: packPawns(yellowPawns),
    },
    houses: {
      Red: houseRed,
      Blue: houseBlue,
      Purple: housePurple,
      Yellow: houseYellow,
    },
  };
}
```

- [ ] **Step 6: Run atlas test**

```bash
( cd frontend && npx vitest run src/render/spriteAtlas.test.ts )
```
Expected: 2 passed.

- [ ] **Step 7: Run full frontend suite + typecheck**

```bash
( cd frontend && npm test )
( cd frontend && npx tsc --noEmit )
```
Expected: 38 passed (36 + 2 new). No type errors.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/render/spriteAtlas.ts frontend/src/render/spriteAtlas.test.ts
git commit -m "$(cat <<'EOF'
feat(atlas): load 4 colors × 4 pawn variants (16 sheets)

New atlas.pawns[ColonyPalette][PawnVariant] shape. Idle + Run + Idle_Meat
+ Run_Meat for Red/Blue/Purple/Yellow. Legacy atlas.pawn kept as Blue
idle so existing render paths don't break before the per-colony lookup
lands in the renderer.

+~500KB bundle (demo-only; no prod first-paint concern).
EOF
)"
```

---

### Task 10: animConfig.ts constants

**Files:**
- Create: `frontend/src/render/animConfig.ts`.

- [ ] **Step 1: Create the file**

Create `frontend/src/render/animConfig.ts`:
```typescript
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
```

- [ ] **Step 2: Run typecheck**

```bash
( cd frontend && npx tsc --noEmit )
```
Expected: clean.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/render/animConfig.ts
git commit -m "$(cat <<'EOF'
feat(render): add animConfig with FRAME_MS, FRAMES_PER_CYCLE, STATE_ICON_MAP

Constants consumed by the next tasks: renderer frame cycler and state
icon overlay. Icon map covers the definitive engine state set
(IDLE/RESTING/FORAGING/SOCIALISING/EXPLORING/TRAVERSING/PLANTING/
HARVESTING/DEPOSITING/EATING/DEAD). IDLE = empty string, guarded at
draw time to skip fillText.
EOF
)"
```

---

## Phase D — Frontend animation

### Task 11: Renderer per-agent anim state + frame cycler + variant picker

**Files:**
- Modify: `frontend/src/render/Canvas2DRenderer.ts` — add anim state map, frame cycler, `pickVariant`, palette-aware sheet selection.
- Modify: `frontend/src/render/Canvas2DRenderer.test.ts` — add pickVariant + cycler tests.

- [ ] **Step 1: Read the current Canvas2DRenderer agent-draw section**

Run: `grep -n "drawFrame\|drawAgent\|pawn\|prevPositions" frontend/src/render/Canvas2DRenderer.ts | head -20`

Locate:
- Where `this.sprites.pawn` is drawn (the current single-sheet pawn draw).
- Where `prevPositions` is tracked (for interpolation).
- Where `drawFrame` iterates agents.

- [ ] **Step 2: Add anim state fields to the class + pickVariant helper**

In the renderer class (near the other per-agent state maps — e.g. `prevPositions`):
```typescript
import { FRAME_MS, FRAMES_PER_CYCLE } from './animConfig';
import type { ColonyPalette, PawnVariant } from './spriteAtlas';

interface AnimState {
  variant: PawnVariant;
  frameIndex: number;
  elapsedMs: number;
}

// Add as a class property:
private animStates: Map<number, AnimState> = new Map();
```

Add a private static helper (or a module-level function) for variant picking:
```typescript
function pickVariant(
  agent: { state: string; cargo?: number; x: number; y: number },
  prev: { x: number; y: number } | undefined,
): PawnVariant {
  const moving = prev !== undefined && (agent.x !== prev.x || agent.y !== prev.y);
  const carrying = (agent.cargo ?? 0) > 0;
  if (moving && carrying) return 'runMeat';
  if (moving) return 'run';
  if (carrying) return 'idleMeat';
  return 'idle';
}
```

- [ ] **Step 3: Write the pickVariant test**

Append to `frontend/src/render/Canvas2DRenderer.test.ts`:
```typescript
// pickVariant isn't exported — test via the renderer if it is; otherwise
// export pickVariant from the module (pragmatic choice for unit testing).
import { pickVariant } from './Canvas2DRenderer';

describe('pickVariant', () => {
  const baseAgent = { state: 'exploring', x: 1, y: 1, cargo: 0 };

  it('returns idle when stationary with no cargo', () => {
    expect(pickVariant(baseAgent, { x: 1, y: 1 })).toBe('idle');
  });

  it('returns idleMeat when stationary with cargo', () => {
    expect(pickVariant({ ...baseAgent, cargo: 2 }, { x: 1, y: 1 })).toBe('idleMeat');
  });

  it('returns run when moving, no cargo', () => {
    expect(pickVariant(baseAgent, { x: 0, y: 1 })).toBe('run');
  });

  it('returns runMeat when moving with cargo', () => {
    expect(pickVariant({ ...baseAgent, cargo: 3 }, { x: 0, y: 1 })).toBe('runMeat');
  });

  it('returns idle when prev is undefined (first frame)', () => {
    expect(pickVariant(baseAgent, undefined)).toBe('idle');
  });
});
```

Export `pickVariant` from `Canvas2DRenderer.ts` so the test can import it (add `export` in front of the function declaration).

- [ ] **Step 4: Add frame cycler logic in drawFrame**

In the `drawFrame` method (or wherever the per-agent loop lives), before the sprite draw:
```typescript
// Advance anim state for each agent (or create on first sight).
const dt = /* ms since last frame — compute from performance.now() or passed-in dt */;
for (const agent of snap.agents) {
  if (!agent.alive) continue;
  const prev = this.prevPositions.get(agent.id);
  const wantVariant = pickVariant(agent, prev);

  let anim = this.animStates.get(agent.id);
  if (!anim || anim.variant !== wantVariant) {
    // First sight OR variant changed → reset to frame 0.
    anim = { variant: wantVariant, frameIndex: 0, elapsedMs: 0 };
    this.animStates.set(agent.id, anim);
  } else {
    anim.elapsedMs += dt;
    while (anim.elapsedMs >= FRAME_MS) {
      anim.frameIndex = (anim.frameIndex + 1) % FRAMES_PER_CYCLE;
      anim.elapsedMs -= FRAME_MS;
    }
  }
}

// Sweep: delete anim entries for agents no longer in the snapshot
// (died or left the sim). Prevents unbounded Map growth.
const aliveIds = new Set(snap.agents.map(a => a.id));
for (const id of Array.from(this.animStates.keys())) {
  if (!aliveIds.has(id)) this.animStates.delete(id);
}
```

- [ ] **Step 5: Use anim state + palette in the pawn draw**

Find the existing pawn draw (where `this.sprites.pawn` is used). Replace the sprite source + source-X offset:
```typescript
// Replace: const sheet = this.sprites.pawn;
// With:
const palette = (colony?.sprite_palette as ColonyPalette | undefined) ?? 'Blue';
const palettePawns = this.sprites.pawns[palette] ?? this.sprites.pawns.Blue;
const anim = this.animStates.get(agent.id)!;
const sheet = palettePawns[anim.variant];
const sx = anim.frameIndex * PAWN_FRAME_PX;        // 192 × frameIndex
// sy stays 0 (8 frames horizontal, 1 row).
ctx.drawImage(sheet, sx, 0, PAWN_FRAME_PX, PAWN_FRAME_PX,
              dx, dy, drawSize, drawSize);
```

`colony` here is the colony object for `agent.colony_id` — the renderer already looks it up (grep `colonies` in the draw path). If not, pass the colonies array into drawFrame and look up by `agent.colony_id`.

- [ ] **Step 6: Run tests**

```bash
( cd frontend && npx vitest run src/render/Canvas2DRenderer.test.ts )
```
Expected: new pickVariant tests pass; existing renderer tests still green.

If existing tests broke (e.g. relied on `this.sprites.pawn`), rebase them onto the new shape by reading `atlas.pawns.Blue.idle` or equivalent.

- [ ] **Step 7: Run full frontend suite**

```bash
( cd frontend && npm test && npx tsc --noEmit )
```
Expected: ≥43 passed; typecheck clean.

- [ ] **Step 8: Manual visual check**

```bash
docker compose up -d
# Open http://localhost
# Create a 4-colony sim (Red/Blue/Purple/Yellow), press Play.
# Verify:
#   (a) Each colony's pawns render in their sprite color (not all Blue).
#   (b) Moving pawns cycle through 8 frames (~10 fps).
#   (c) An agent that forages until cargo > 0 swaps to Pawn_*_Meat sprite.
```

- [ ] **Step 9: Commit**

```bash
git add frontend/src/render/Canvas2DRenderer.ts frontend/src/render/Canvas2DRenderer.test.ts
git commit -m "$(cat <<'EOF'
feat(render): per-agent animation cycling with cargo + palette aware sprites

Per-agent AnimState tracks variant + frameIndex + elapsedMs. pickVariant
derives motion from position delta (not state-string — see spec for why
MOVING_STATES was wrong). Variant changes reset to frame 0.

Palette lookup via colony.sprite_palette, fallback Blue. Cargo > 0 swaps
to *_Meat variant so the agent visibly carries food.

Manually verified: 4-color sim plays correctly.
EOF
)"
```

---

### Task 12: State icon overlay (draw-guarded)

**Files:**
- Modify: `frontend/src/render/Canvas2DRenderer.ts` — add `_drawStateIcon` helper, call after sprite.

- [ ] **Step 1: Add the draw helper**

In the renderer class (near other `_draw*` helpers):
```typescript
import { STATE_ICON_MAP } from './animConfig';

private _drawStateIcon(
  ctx: CanvasRenderingContext2D,
  state: string,
  cx: number,
  baseY: number,
  phase: string,
) {
  const glyph = STATE_ICON_MAP[state] ?? '';
  if (!glyph) return;                   // draw-guard — no fillText('')
  ctx.save();
  ctx.globalAlpha = phase === 'night' ? 0.4 : 1.0;
  ctx.font = '18px system-ui, sans-serif';
  ctx.textAlign = 'center';
  ctx.fillStyle = '#ffffff';
  ctx.fillText(glyph, cx, baseY - 18);
  ctx.restore();
}
```

- [ ] **Step 2: Call the helper after each agent's sprite draw**

In `drawFrame`, after the `ctx.drawImage(sheet, ...)` line added in Task 11:
```typescript
this._drawStateIcon(ctx, agent.state, dx + drawSize / 2, dy, snap.phase ?? 'day');
```

`snap.phase` is the current phase from the snapshot. If the snapshot doesn't carry phase, either thread it in or read from `snap.sim.phase`.

- [ ] **Step 3: Manual visual check**

```bash
# Keep dev stack up from Task 11.
# Hard-reload browser (Ctrl+Shift+R).
# Verify:
#   - Resting agents show 💤 above them.
#   - Foraging agents show 🌾.
#   - Planting/harvesting show the leaf/wheat glyph.
#   - Night: icons fade to ~40% opacity.
#   - Truly idle agents (between decisions) show no glyph.
```

- [ ] **Step 4: Run frontend tests (smoke)**

```bash
( cd frontend && npm test )
```
Expected: tests still green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/render/Canvas2DRenderer.ts
git commit -m "$(cat <<'EOF'
feat(render): state icon overlay above each agent

Renders STATE_ICON_MAP glyph above the sprite at y - 18px. Guards the
fillText call when glyph is empty (idle state between decisions).
Night-phase opacity drops to 40% so the overlay doesn't fight the
day/night tint.
EOF
)"
```

---

## Phase E — Hover UX

### Task 13: Hover state in WorldCanvas + pixel-to-agent lookup

**Files:**
- Modify: `frontend/src/components/WorldCanvas.tsx`.

- [ ] **Step 1: Add hover state and pointermove handler**

In `WorldCanvas.tsx`, in the component body, near the existing `dragRef`:
```typescript
import { useState } from 'react';

interface HoverState {
  agent: Agent;
  colony: Colony | undefined;
  screenX: number;
  screenY: number;
}

const [hover, setHover] = useState<HoverState | null>(null);
const lastMoveTsRef = useRef(0);
```

- [ ] **Step 2: Extract pixel-to-tile helper**

Near the top of the component (or at module scope):
```typescript
function pixelToTile(
  px: number, py: number,
  snap: { cameraX: number; cameraY: number; tilePx: number },
): { x: number; y: number } {
  return {
    x: Math.floor((px - snap.cameraX) / snap.tilePx),
    y: Math.floor((py - snap.cameraY) / snap.tilePx),
  };
}
```

- [ ] **Step 3: Add the handler in the existing effect that binds pointer events**

In the same `useEffect` that registers `pointerdown`/`pointerup`/`wheel`, add:
```typescript
const onPointerMoveHover = (e: PointerEvent) => {
  if (dragRef.current) {
    setHover(null);
    return;
  }
  const now = performance.now();
  if (now - lastMoveTsRef.current < 16) return;    // ~60fps throttle
  lastMoveTsRef.current = now;

  const snap = snapRef.current;
  if (!snap) return;

  const rect = canvas.getBoundingClientRect();
  const localX = e.clientX - rect.left;
  const localY = e.clientY - rect.top;
  const tile = pixelToTile(localX, localY, snap);

  const agent = snap.agents.find(
    a => a.alive && a.x === tile.x && a.y === tile.y,
  );
  if (!agent) {
    setHover(null);
    return;
  }
  const colony = snap.colonies.find(c => c.id === agent.colony_id);
  setHover({
    agent,
    colony,
    screenX: e.clientX,
    screenY: e.clientY,
  });
};

const onPointerLeave = () => setHover(null);

canvas.addEventListener('pointermove', onPointerMoveHover);
canvas.addEventListener('pointerleave', onPointerLeave);
```

And in the cleanup return:
```typescript
canvas.removeEventListener('pointermove', onPointerMoveHover);
canvas.removeEventListener('pointerleave', onPointerLeave);
```

Also, clear hover at the start of `onPointerDown`:
```typescript
const onPointerDown = (e: PointerEvent) => {
  setHover(null);
  // ... existing body ...
};
```

- [ ] **Step 4: Render the tooltip (placeholder for now)**

At the end of the `return (...)` JSX, just before the closing tag:
```tsx
{hover && (
  <div
    style={{
      position: 'fixed',
      left: hover.screenX + 8,
      top: hover.screenY + 8,
      padding: '4px 8px',
      background: '#111',
      color: '#fff',
      fontSize: 12,
      pointerEvents: 'none',
      zIndex: 20,
    }}
  >
    {hover.agent.name} — {hover.agent.state}
  </div>
)}
```

(Task 14 replaces this with the full `AgentTooltip` component.)

- [ ] **Step 5: Run tests + manual check**

```bash
( cd frontend && npm test && npx tsc --noEmit )
```

Manual: in the running sim, hover over a pawn → placeholder tooltip appears with name + state; leaves → disappears; drag-start → disappears.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/WorldCanvas.tsx
git commit -m "$(cat <<'EOF'
feat(canvas): pointermove hover + pixel-to-agent lookup

60fps-throttled pointermove handler; pixel→tile→agent lookup O(n) at
demo scale. Clears on drag-start (pointerdown) and on pointerleave.
Placeholder tooltip renders name+state — replaced by AgentTooltip in
the next commit.
EOF
)"
```

---

### Task 14: AgentTooltip component (decision_reason + dual-axis clamp)

**Files:**
- Create: `frontend/src/components/AgentTooltip.tsx`.
- Create: `frontend/src/components/AgentTooltip.test.tsx`.
- Modify: `frontend/src/components/WorldCanvas.tsx` — replace placeholder with `<AgentTooltip />`.
- Modify: `frontend/src/styles.css` — add `.agent-tooltip` rules.

- [ ] **Step 1: Write the tooltip component test**

Create `frontend/src/components/AgentTooltip.test.tsx`:
```tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { AgentTooltip } from './AgentTooltip';
import type { Agent, Colony } from '../api/types';

const baseAgent: Agent = {
  id: 1, name: 'Alice', x: 2, y: 2, state: 'foraging',
  hunger: 47, energy: 80, social: 65, health: 90, age: 12,
  alive: true, colony_id: 1, rogue: false, loner: false, cargo: 2.5,
  decision_reason: 'hunger < 50 → forage',
};

const baseColony: Colony = {
  id: 1, name: 'Red', color: '#e74c3c', camp_x: 3, camp_y: 3,
  food_stock: 18, growing_count: 0, sprite_palette: 'Red',
};

describe('AgentTooltip', () => {
  it('renders agent name and colony name', () => {
    render(<AgentTooltip agent={baseAgent} colony={baseColony} screenX={100} screenY={100} />);
    expect(screen.getByText('Alice')).toBeInTheDocument();
    expect(screen.getByText('Red')).toBeInTheDocument();
  });

  it('renders state', () => {
    render(<AgentTooltip agent={baseAgent} colony={baseColony} screenX={100} screenY={100} />);
    expect(screen.getByText(/foraging/)).toBeInTheDocument();
  });

  it('renders cargo line when cargo > 0', () => {
    render(<AgentTooltip agent={baseAgent} colony={baseColony} screenX={100} screenY={100} />);
    expect(screen.getByText(/cargo/i)).toBeInTheDocument();
  });

  it('omits cargo line when cargo is 0', () => {
    const noCargo = { ...baseAgent, cargo: 0 };
    render(<AgentTooltip agent={noCargo} colony={baseColony} screenX={100} screenY={100} />);
    expect(screen.queryByText(/cargo/i)).not.toBeInTheDocument();
  });

  it('renders decision_reason when non-empty', () => {
    render(<AgentTooltip agent={baseAgent} colony={baseColony} screenX={100} screenY={100} />);
    expect(screen.getByText(baseAgent.decision_reason)).toBeInTheDocument();
  });

  it('omits decision_reason line when empty', () => {
    const blank = { ...baseAgent, decision_reason: '' };
    render(<AgentTooltip agent={blank} colony={baseColony} screenX={100} screenY={100} />);
    // Nothing special to assert — just confirm render doesn't crash.
    expect(screen.getByText('Alice')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test — fails (file doesn't exist)**

```bash
( cd frontend && npx vitest run src/components/AgentTooltip.test.tsx )
```
Expected: FAIL.

- [ ] **Step 3: Create `AgentTooltip.tsx`**

Create `frontend/src/components/AgentTooltip.tsx`:
```tsx
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
  const { left, top } = clamp(
    screenX, screenY,
    TOOLTIP_W, TOOLTIP_H,
    typeof window !== 'undefined' ? window.innerWidth : 1920,
    typeof window !== 'undefined' ? window.innerHeight : 1080,
  );
  const glyph = STATE_ICON_MAP[agent.state] ?? '';

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
      {(agent.cargo ?? 0) > 0 && (
        <div className="agent-tooltip__cargo">
          cargo {(agent.cargo ?? 0).toFixed(1)} / {CARRY_MAX}
        </div>
      )}
      {agent.decision_reason && (
        <div className="agent-tooltip__reason">{agent.decision_reason}</div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Add CSS in `styles.css`**

Append to `frontend/src/styles.css`:
```css
.agent-tooltip {
  position: fixed;
  min-width: 180px;
  max-width: 220px;
  padding: 6px 8px;
  background: rgba(10, 12, 18, 0.95);
  color: #e6e8ec;
  font-family: system-ui, sans-serif;
  font-size: 12px;
  line-height: 1.3;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 4px;
  pointer-events: none;
  z-index: 20;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.35);
}

.agent-tooltip__head {
  display: flex;
  gap: 6px;
  align-items: center;
  margin-bottom: 4px;
}

.agent-tooltip__name { font-weight: 600; }

.agent-tooltip__pill {
  font-size: 10px;
  padding: 1px 4px;
  border-radius: 2px;
  color: #fff;
}

.agent-tooltip__state { margin-bottom: 4px; opacity: 0.9; }
.agent-tooltip__icon { margin-right: 3px; }

.agent-tooltip__bars { display: flex; flex-direction: column; gap: 1px; }
.agent-tooltip__meter { display: flex; gap: 4px; align-items: baseline; }
.agent-tooltip__meter-label { width: 42px; opacity: 0.7; }
.agent-tooltip__meter-bar  { font-family: monospace; letter-spacing: -1px; }
.agent-tooltip__meter-value { width: 24px; text-align: right; opacity: 0.7; }

.agent-tooltip__cargo { margin-top: 3px; color: #ffb37b; }

.agent-tooltip__reason {
  margin-top: 4px;
  padding-top: 3px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  font-size: 11px;
  opacity: 0.75;
}
```

- [ ] **Step 5: Replace placeholder in WorldCanvas with AgentTooltip**

In `WorldCanvas.tsx`:
```tsx
import { AgentTooltip } from './AgentTooltip';

// Replace the placeholder div with:
{hover && (
  <AgentTooltip
    agent={hover.agent}
    colony={hover.colony}
    screenX={hover.screenX}
    screenY={hover.screenY}
  />
)}
```

- [ ] **Step 6: Run tests**

```bash
( cd frontend && npx vitest run src/components/AgentTooltip.test.tsx )
( cd frontend && npm test && npx tsc --noEmit )
```
Expected: tooltip tests 6 passed; full suite 44+ passed; typecheck clean.

- [ ] **Step 7: Manual visual check**

```bash
# Browser: hover over pawns in the running sim.
# Verify:
#   - Tooltip appears within ~100ms after hover.
#   - Shows name, colony pill, state, 4 mini-bars, cargo (if > 0), reason.
#   - Near right edge → tooltip mirrors to left of cursor.
#   - Near bottom edge → tooltip mirrors above cursor.
#   - Drag-start → tooltip disappears.
#   - Leave canvas → disappears.
```

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/AgentTooltip.tsx frontend/src/components/AgentTooltip.test.tsx frontend/src/components/WorldCanvas.tsx frontend/src/styles.css
git commit -m "$(cat <<'EOF'
feat(hud): AgentTooltip with decision_reason + dual-axis clamp

Hover tooltip over canvas pawns. Surfaces name, colony pill, state,
mini-bars for hunger/energy/social/health, cargo (when > 0), and
decision_reason (when non-empty). Dual-axis viewport clamp mirrors the
tooltip to the left/above the cursor near screen edges.

6 tooltip unit tests cover the render contract.
EOF
)"
```

---

### Task 15: AgentPanel decision-reason readout

**Files:**
- Modify: `frontend/src/components/AgentPanel.tsx`.
- Create: `frontend/src/components/AgentPanel.test.tsx` (does not exist pre-plan; the adjacent `ColonyPanel.test.tsx` is the closest prior art — mount via QueryClientProvider + seed the query cache).
- Modify: `frontend/src/styles.css` — `.decision-reason`.

- [ ] **Step 1: Write the panel test (complete file)**

Create `frontend/src/components/AgentPanel.test.tsx` with the full harness — mount the panel, seed the agents query cache, set the view store's selected agent id, and assert on the rendered text:

```tsx
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { AgentPanel } from './AgentPanel';
import { useViewStore } from '../state/viewStore';
import type { Agent } from '../api/types';

const baseAgent: Agent = {
  id: 1, name: 'Alice', x: 2, y: 2, state: 'foraging',
  hunger: 47, energy: 80, social: 65, health: 90, age: 12,
  alive: true, colony_id: 1, rogue: false, loner: false, cargo: 2.5,
  decision_reason: 'hunger < 50 → forage',
};

function mountWith(agent: Agent) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  // Seed the agents query cache. useAgents() keys on ['worldState'] and
  // pulls `.agents` — seed the whole composite shape; unused branches are
  // tolerated because the panel only reads `agent`.
  qc.setQueryData(['worldState'], {
    sim: null, world: null, agents: [agent], colonies: [], events: [],
  });
  // Pick this agent via the view store.
  useViewStore.getState().selectAgent(agent.id);

  return render(
    <QueryClientProvider client={qc}>
      <AgentPanel />
    </QueryClientProvider>,
  );
}

describe('AgentPanel decision_reason', () => {
  beforeEach(() => {
    useViewStore.getState().selectAgent(null);   // reset between tests
  });

  it('renders decision_reason below the state pill when non-empty', () => {
    mountWith(baseAgent);
    expect(screen.getByText('hunger < 50 → forage')).toBeInTheDocument();
  });

  it('hides decision_reason when empty string', () => {
    mountWith({ ...baseAgent, decision_reason: '' });
    expect(screen.queryByText(/→/)).not.toBeInTheDocument();
  });
});
```

*Note on `useAgents` query key:* the panel reads `useAgents()` which internally calls `useQuery({ queryKey: ['worldState'], ... select: (r) => r.agents })` per the existing `api/queries.ts`. The composite query key is `['worldState']` — seed that shape above. If the implementer finds the actual key/select differs after running the test, adjust the `qc.setQueryData(...)` call to match — grep `worldStateQuery` in `api/queries.ts` for the real shape.

- [ ] **Step 2: Run the test — expect FAIL**

```bash
( cd frontend && npx vitest run src/components/AgentPanel.test.tsx )
```
Expected: FAIL on missing reason text.

- [ ] **Step 3: Update `AgentPanel.tsx`**

In the panel, find the `<dt>state</dt><dd>…</dd>` block. Add the reason line inside the `<dd>`:

```tsx
import { STATE_ICON_MAP } from '../render/animConfig';

// ... inside the return:
<dt>state</dt>
<dd>
  <span className={`pill ${agent.alive ? 'pill--alive' : 'pill--dead'}`}>
    {STATE_ICON_MAP[agent.state] ?? ''} {agent.alive ? agent.state : 'deceased'}
  </span>
  {/* rogue/loner badges — unchanged */}
  {agent.alive && agent.rogue && (
    <span className="pill" style={{ marginLeft: 6, background: '#4a1a1a', color: '#ff8f6b' }}
          title="Social need collapsed to zero — cannot return home">
      rogue
    </span>
  )}
  {agent.alive && agent.loner && !agent.rogue && (
    <span className="pill" style={{ marginLeft: 6, background: '#1f2933', color: '#9fb4d0' }}
          title="Social need decays faster than normal">
      loner
    </span>
  )}
  {agent.decision_reason && (
    <div className="decision-reason">{agent.decision_reason}</div>
  )}
</dd>
```

- [ ] **Step 4: Add `.decision-reason` CSS**

Append to `frontend/src/styles.css`:
```css
.decision-reason {
  margin-top: 3px;
  font-size: 11px;
  color: rgba(230, 232, 236, 0.6);
  line-height: 1.3;
}
```

- [ ] **Step 5: Run tests**

```bash
( cd frontend && npx vitest run src/components/AgentPanel.test.tsx )
( cd frontend && npm test && npx tsc --noEmit )
```
Expected: panel tests pass; full suite stays green.

- [ ] **Step 6: Manual visual check**

```bash
# In the running sim, click on a pawn.
# Verify:
#   - State pill shows the state glyph + label.
#   - A muted one-line reason appears below the state row.
#   - Reason updates as the sim ticks (every engine decision refreshes it).
```

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/AgentPanel.tsx frontend/src/components/AgentPanel.test.tsx frontend/src/styles.css
git commit -m "$(cat <<'EOF'
feat(panel): decision_reason line below state pill

AgentPanel now renders the engine's one-line explanation of the
current action under the state pill. Hidden when reason is empty
(pre-first-tick default). State pill also picks up the state glyph.
EOF
)"
```

---

## Phase F — Final manual verification

### Task 16: End-to-end manual test + baseline lock

**Files:** none (verification only).

- [ ] **Step 1: Stop + rebuild + start the stack cleanly**

```bash
docker compose down
docker compose up --build -d
docker compose run --rm flask flask db upgrade
```

Wait ~10 seconds for services to be ready.

- [ ] **Step 2: Run full backend suite**

```bash
docker compose run --rm flask pytest -q
```
Expected output ends with: `N passed in …` where N = baseline (227) + all new tests added across Tasks 1-15 (at minimum: 3 Decision + 15 reason + 1 tick_set + 2 mapper + 2 colony palette + 2 colony mapper + 2 atlas + 6 tooltip = adds ≥ 33). Target **≥260 passed**.

- [ ] **Step 3: Run full frontend suite + typecheck**

```bash
( cd frontend && npm test && npx tsc --noEmit )
```
Expected output: `Tests  N passed` where N ≥ 44 (36 + 2 atlas + 6 tooltip + 2 panel = 46). Typecheck: clean.

- [ ] **Step 4: Open browser, 4-colony demo walkthrough**

Go to `http://localhost`. Create a simulation: width 40, height 30, seed 42, 4 colonies, 3 agents per colony. Press Play. Observe for ~2 minutes.

Check off:
- [ ] Each colony's pawns render in distinct colors (Red, Blue, Purple, Yellow).
- [ ] Idle pawns cycle through 8 frames (~10 fps head-bob).
- [ ] Moving pawns cycle through the Run sprite set.
- [ ] An agent with cargo > 0 shows the `_Meat` sprite variant (visible meat in hand).
- [ ] State icons appear above pawns: 💤 resting, 🌾 foraging, 🌱 planting, 📦 depositing, 🍖 eating, 💬 socialising, · exploring.
- [ ] Night phase: state icons fade (40% opacity).
- [ ] Hover over a pawn → tooltip within ~100 ms showing name, colony pill, state, mini-bars, cargo (if any), decision reason.
- [ ] Tooltip near screen right edge → mirrors to the left of cursor.
- [ ] Tooltip near screen bottom edge → mirrors above cursor.
- [ ] Click a pawn → AgentPanel opens with state pill + muted decision-reason line below.
- [ ] Reason updates as the agent transitions (e.g. hungry → forage → cargo → deposit → explore).

- [ ] **Step 5: If everything passes, tag the cleanup-demo state**

```bash
git tag agent-shine-round3
git log --oneline 787e974..HEAD
```

- [ ] **Step 6: Commit any cleanup (if needed) + push**

If there are doc touch-ups or CSS tweaks, commit them now. Then ask the user whether to push to `origin/master`:

```bash
git status    # verify clean
git push origin master                      # only if user confirms
git push origin agent-shine-round3
```

*User review gate — don't push without explicit confirmation.*

---

## Summary table (for tracking)

| Task | Component | LOC delta (est) | Tests added | Manual check |
|------|-----------|-----------------|-------------|--------------|
| 1 | Decision dataclass | +12 backend | +3 | — |
| 2 | decide_action refactor + caller migration | ~0 net (restructure) | 0 (rewires 20 callers) | — |
| 3 | Per-branch reason tests | +150 test | +15 | — |
| 4 | last_decision_reason slot | +4 backend, +15 test | +1 | — |
| 5 | agent decision_reason field + type | +4 backend, +1 frontend | +2 | — |
| 6 | Colony.sprite_palette schema | +3 model, +30 migration | 0 (schema) | — |
| 7 | EngineColony palette + default | +12 engine | +2 | — |
| 8 | Mapper round-trip + colony dict + type | +6 backend, +1 frontend | +2 | — |
| 9 | Sprite atlas 16 sheets | +80 frontend, +30 test | +2 | — |
| 10 | animConfig.ts | +30 frontend | 0 | — |
| 11 | Renderer anim cycling + variant | +60 frontend, +30 test | +5 | Visual: color + cycle |
| 12 | State icon overlay | +20 frontend | 0 | Visual: icons + night opacity |
| 13 | WorldCanvas pointermove hover | +60 frontend | 0 | Visual: placeholder tooltip |
| 14 | AgentTooltip component + CSS | +120 frontend, +80 test | +6 | Visual: full tooltip |
| 15 | AgentPanel reason readout | +8 frontend, +30 test | +2 | Visual: reason in panel |
| 16 | End-to-end manual | 0 | 0 | Full walkthrough |

**Target baseline after completion:** ≥260 backend + ≥46 frontend.

**Target date to ship:** 2026-04-27 (Mon) — leaves 1 day buffer for the 2026-04-28 re-demo.
