# Day/Night Cycle + Multi-Colony Cultivation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a 120-tick diurnal cycle and multi-colony scarcity-driven cultivation to the existing colony sim, in time for the 2026-04-17 interview demo.

**Architecture:** Pure-engine additions (new `cycle.py`, extended `decide_action`, new `plant`/`harvest`/`eat_camp` actions, world-level `tick(phase)` for crop growth) driven by a derived `phase` from `current_tick`. Data layer gains a `colonies` table and two columns on `world_tiles`. Service layer applies colony-stock mutations from engine event payloads (mirroring the existing §9.19 dirty-tile pattern). Frontend adds a ClockWidget, phase tint overlay, per-colony agent/camp tint, binary crop overlay, and a per-colony HUD panel.

**Tech Stack:** Python 3.12, Flask, Flask-SQLAlchemy 3.x, Alembic (Flask-Migrate), PostgreSQL 18, React 18 + TypeScript, Zustand, React Query, Vite, Vitest, pytest.

**Spec:** `docs/superpowers/specs/2026-04-15-day-night-cultivation-design.md`

---

## File Structure

**Backend — engine (pure Python, no Flask/DB):**
- `backend/app/engine/cycle.py` — CREATE: `phase_for(tick)`, `day_for(tick)`, constants
- `backend/app/engine/config.py` — CREATE: balance constants (`HARVEST_YIELD`, `INITIAL_FOOD_STOCK`, etc.)
- `backend/app/engine/colony.py` — CREATE: `EngineColony` dataclass-like pure class
- `backend/app/engine/needs.py` — MODIFY: add `NIGHT_HUNGER_SCALE`
- `backend/app/engine/world.py` — MODIFY: `Tile` gains `crop_state`, `crop_growth_ticks`, `crop_colony_id`; `World.tick(phase)`
- `backend/app/engine/actions.py` — MODIFY: add `plant`, `harvest`, `eat_camp`; re-use existing `step_toward`
- `backend/app/engine/agent.py` — MODIFY: `Agent.__slots__` adds `colony_id`; `decide_action` signature gains `phase`, `colony`, `world`; `tick_agent` receives phase + colonies
- `backend/app/engine/simulation.py` — MODIFY: `Simulation.colonies`; `Simulation.step()` calls `world.tick(phase)` and threads phase/colony into tick_agent; `new_simulation` takes colony args

**Backend — ORM (models.py split):**
- `backend/app/models/colony.py` — CREATE: `Colony` model
- `backend/app/models/__init__.py` — MODIFY: export `Colony`
- `backend/app/models/agent.py` — MODIFY: `colony_id` FK
- `backend/app/models/world.py` — MODIFY: `crop_state`, `crop_growth_ticks`, `crop_colony_id` cols

**Backend — migration:**
- `backend/migrations/versions/d4e5f6a7b8c9_colonies_crops.py` — CREATE

**Backend — services:**
- `backend/app/services/mappers.py` — MODIFY: `colony_to_row`/`row_to_colony`/`update_colony_row`; extended `tile_to_row`/`row_to_tile` for crop cols + colony_id; extended agent mappers for colony_id
- `backend/app/services/simulation_service.py` — MODIFY: `create_simulation` signature (`colonies`, `agents_per_colony`); event→DB wiring for new events; dirty-colony set

**Backend — routes:**
- `backend/app/routes/serializers.py` — MODIFY: `colony_to_dict`, `simulation_summary` gains `day`/`phase`, `agent_to_dict` gains `colony_id`, `tile_to_dict` gains crop fields
- `backend/app/routes/simulation.py` — MODIFY: `PUT /simulation` accepts `colonies`, `agents_per_colony`; `GET /world/state` response gains colonies

**Backend — tests:**
- `backend/tests/engine/test_cycle.py` — CREATE
- `backend/tests/engine/test_world_tick.py` — CREATE
- `backend/tests/engine/test_actions_plant_harvest.py` — CREATE
- `backend/tests/engine/test_decide_action_phase.py` — CREATE
- `backend/tests/engine/test_dawn_eat.py` — CREATE
- `backend/tests/engine/test_night_decay.py` — CREATE
- `backend/tests/engine/test_dusk_pathing.py` — CREATE
- `backend/tests/services/test_simulation_service.py` — MODIFY (extend with new cases)
- `backend/tests/routes/test_simulation_routes.py` — MODIFY (extend with colony/phase cases)
- `backend/tests/integration/test_cultivation_arc.py` — CREATE

**Frontend:**
- `frontend/src/api/types.ts` — MODIFY: `Colony`, `Phase`, `sim.day/phase`, `tile.crop_state/crop_growth_ticks/crop_colony_id`, `agent.colony_id`, `WorldStateResponse.colonies`
- `frontend/src/components/ClockWidget.tsx` — CREATE
- `frontend/src/components/ColonyPanel.tsx` — CREATE
- `frontend/src/styles.css` — MODIFY: `.phase-dawn`, `.phase-day`, `.phase-dusk`, `.phase-night`, `.phase-tint` rules, `.colony-panel` rules
- `frontend/src/App.tsx` — MODIFY: wire ClockWidget, ColonyPanel, phase tint overlay
- `frontend/src/render/Canvas2DRenderer.ts` — MODIFY: agent tint by colony, camp square, crop overlay
- `frontend/src/render/Renderer.ts` — MODIFY: `FrameSnapshot` adds `colonies`, `phase`

---

## Test Commands

Run inside `flask` container (source mounted at `/app`):

```bash
docker compose run --rm flask pytest <path>           # one file / node
docker compose run --rm flask pytest -q               # whole backend suite
```

Frontend (from `frontend/`):
```bash
npx tsc --noEmit                                       # typecheck
npm test                                               # vitest
```

---

# Phase 0 — Engine pure layer

### Task 1: Cycle math module

**Files:**
- Create: `backend/app/engine/cycle.py`
- Test: `backend/tests/engine/test_cycle.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/engine/test_cycle.py
from app.engine import cycle


def test_constants_sum_to_day_length():
    assert cycle.TICKS_PER_DAY == cycle.TICKS_PER_PHASE * len(cycle.PHASES)
    assert cycle.TICKS_PER_DAY == 120
    assert cycle.TICKS_PER_PHASE == 30
    assert cycle.PHASES == ('dawn', 'day', 'dusk', 'night')


def test_phase_for_returns_correct_phase_at_boundaries():
    assert cycle.phase_for(0) == 'dawn'
    assert cycle.phase_for(29) == 'dawn'
    assert cycle.phase_for(30) == 'day'
    assert cycle.phase_for(59) == 'day'
    assert cycle.phase_for(60) == 'dusk'
    assert cycle.phase_for(89) == 'dusk'
    assert cycle.phase_for(90) == 'night'
    assert cycle.phase_for(119) == 'night'
    assert cycle.phase_for(120) == 'dawn'   # wraps
    assert cycle.phase_for(240) == 'dawn'


def test_day_for_increments_each_full_cycle():
    assert cycle.day_for(0) == 0
    assert cycle.day_for(119) == 0
    assert cycle.day_for(120) == 1
    assert cycle.day_for(239) == 1
    assert cycle.day_for(240) == 2
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose run --rm flask pytest tests/engine/test_cycle.py -v
```

Expected: ImportError — `cycle` module doesn't exist.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/engine/cycle.py
"""Day/night cycle math. Pure function of current_tick; no state, no I/O.

TICKS_PER_DAY and TICKS_PER_PHASE are the single source of truth for all
diurnal timing. Keep these invariants:
  - TICKS_PER_DAY == TICKS_PER_PHASE * len(PHASES)
  - PHASES order matches in-world narrative: dawn → day → dusk → night
"""
TICKS_PER_PHASE = 30
PHASES = ('dawn', 'day', 'dusk', 'night')
TICKS_PER_DAY = TICKS_PER_PHASE * len(PHASES)


def phase_for(tick):
    return PHASES[(tick % TICKS_PER_DAY) // TICKS_PER_PHASE]


def day_for(tick):
    return tick // TICKS_PER_DAY
```

- [ ] **Step 4: Run test to verify it passes**

```bash
docker compose run --rm flask pytest tests/engine/test_cycle.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/engine/cycle.py backend/tests/engine/test_cycle.py
git commit -m "feat(engine): day/night cycle math (phase_for, day_for)"
```

---

### Task 2: Balance constants module

**Files:**
- Create: `backend/app/engine/config.py`
- Modify: `backend/app/engine/needs.py` (add `NIGHT_HUNGER_SCALE`)

- [ ] **Step 1: Write the failing test**

```python
# Add to backend/tests/engine/test_cycle.py
from app.engine import config, needs


def test_config_has_required_balance_constants():
    assert config.HARVEST_YIELD == 9
    assert config.INITIAL_FOOD_STOCK == 18
    assert config.EAT_COST == 6
    assert config.CROP_MATURE_TICKS == 60
    assert config.WILD_RESOURCE_MAX == 5
    assert config.WILD_TILE_DENSITY == 0.15
    assert config.MAX_FIELDS_PER_COLONY == 4
    # Sanity: stock divides evenly by eat cost so "1 day of reliance" is exact
    assert config.INITIAL_FOOD_STOCK % config.EAT_COST == 0


def test_needs_has_night_hunger_scale():
    assert needs.NIGHT_HUNGER_SCALE == 0.5
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose run --rm flask pytest tests/engine/test_cycle.py::test_config_has_required_balance_constants -v
```

Expected: ImportError on `config` OR AttributeError.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/engine/config.py
"""Tunable balance constants for day/night + cultivation.

See docs/superpowers/specs/2026-04-15-day-night-cultivation-design.md
§"Balance parameters" for derivation. Changing these values shifts the
demo's "who survives by day 5" dynamic — manual calibration required
after any edit.
"""
HARVEST_YIELD = 9
INITIAL_FOOD_STOCK = 18
EAT_COST = 6
CROP_MATURE_TICKS = 60
WILD_RESOURCE_MAX = 5
WILD_TILE_DENSITY = 0.15
MAX_FIELDS_PER_COLONY = 4
```

Add to `backend/app/engine/needs.py` (after `SOCIAL_DECAY`):

```python
# Night-phase hunger scaling: agents decay slower while sleeping. Applied
# in tick_agent via cycle.phase_for; keeps the constant here so needs.py
# remains the single home for all decay-related tuning.
NIGHT_HUNGER_SCALE = 0.5
```

- [ ] **Step 4: Run test to verify it passes**

```bash
docker compose run --rm flask pytest tests/engine/test_cycle.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/engine/config.py backend/app/engine/needs.py backend/tests/engine/test_cycle.py
git commit -m "feat(engine): balance constants for cultivation + night decay scale"
```

---

### Task 3: Tile gains crop fields

**Files:**
- Modify: `backend/app/engine/world.py` (Tile class + constants)
- Test: `backend/tests/engine/test_world_tick.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/engine/test_world_tick.py
from app.engine.world import Tile


def test_tile_default_crop_state_is_none():
    t = Tile(x=0, y=0, terrain='grass')
    assert t.crop_state == 'none'
    assert t.crop_growth_ticks == 0
    assert t.crop_colony_id is None


def test_tile_accepts_crop_fields_in_constructor():
    t = Tile(x=1, y=2, terrain='grass', crop_state='growing',
             crop_growth_ticks=15, crop_colony_id=3)
    assert t.crop_state == 'growing'
    assert t.crop_growth_ticks == 15
    assert t.crop_colony_id == 3
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose run --rm flask pytest tests/engine/test_world_tick.py -v
```

Expected: AttributeError — `crop_state` not in `__slots__`.

- [ ] **Step 3: Write minimal implementation**

Modify `backend/app/engine/world.py` Tile class:

```python
class Tile:
    __slots__ = (
        'x', 'y', 'terrain', 'resource_type', 'resource_amount',
        'crop_state', 'crop_growth_ticks', 'crop_colony_id',
    )

    def __init__(self, x, y, terrain, resource_type=None, resource_amount=0.0,
                 crop_state='none', crop_growth_ticks=0, crop_colony_id=None):
        self.x = x
        self.y = y
        self.terrain = terrain
        self.resource_type = resource_type
        self.resource_amount = resource_amount
        self.crop_state = crop_state
        self.crop_growth_ticks = crop_growth_ticks
        self.crop_colony_id = crop_colony_id

    @property
    def is_walkable(self):
        return self.terrain != 'water'

    def __repr__(self):
        return f"Tile({self.x},{self.y},{self.terrain})"
```

- [ ] **Step 4: Run test to verify it passes**

```bash
docker compose run --rm flask pytest tests/engine/test_world_tick.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/engine/world.py backend/tests/engine/test_world_tick.py
git commit -m "feat(engine): Tile gains crop_state, crop_growth_ticks, crop_colony_id"
```

---

### Task 4: World.tick(phase) drives crop growth

**Files:**
- Modify: `backend/app/engine/world.py` (add `tick` method)
- Test: `backend/tests/engine/test_world_tick.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/engine/test_world_tick.py`:

```python
from app.engine.world import World
from app.engine import config


def _world_with_growing_tile(colony_id=1):
    w = World(5, 5)
    w.tiles = [[Tile(x, y, 'grass') for x in range(5)] for y in range(5)]
    t = w.tiles[2][2]
    t.crop_state = 'growing'
    t.crop_growth_ticks = 0
    t.crop_colony_id = colony_id
    return w, t


def test_world_tick_day_increments_growth():
    w, t = _world_with_growing_tile()
    events = w.tick('day')
    assert t.crop_growth_ticks == 1
    assert events == []      # no maturation yet


def test_world_tick_non_day_does_not_grow():
    for phase in ('dawn', 'dusk', 'night'):
        w, t = _world_with_growing_tile()
        events = w.tick(phase)
        assert t.crop_growth_ticks == 0, f'grew during {phase}'
        assert events == []


def test_world_tick_matures_at_threshold():
    w, t = _world_with_growing_tile()
    # Advance to one below threshold, then one more day-tick should mature.
    t.crop_growth_ticks = config.CROP_MATURE_TICKS - 1
    events = w.tick('day')
    assert t.crop_state == 'mature'
    assert t.resource_amount == config.HARVEST_YIELD
    assert len(events) == 1
    e = events[0]
    assert e['type'] == 'crop_matured'
    assert e['data']['tile_x'] == 2
    assert e['data']['tile_y'] == 2
    assert e['data']['colony_id'] == 1


def test_world_tick_mature_tile_is_idempotent():
    w, t = _world_with_growing_tile()
    t.crop_state = 'mature'
    t.crop_growth_ticks = config.CROP_MATURE_TICKS
    events = w.tick('day')
    # Mature tiles don't grow further or re-emit.
    assert events == []
    assert t.crop_state == 'mature'
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose run --rm flask pytest tests/engine/test_world_tick.py -v
```

Expected: AttributeError — `World` has no `tick` method.

- [ ] **Step 3: Write minimal implementation**

Add to `backend/app/engine/world.py` (in `World` class):

```python
    def tick(self, phase):
        """World-level per-tick logic. Currently: crop growth (day phase only).

        Returns a list of event dicts (e.g. `crop_matured`) emitted this
        tick. Pure: no I/O, deterministic given tile state + phase.
        """
        if phase != 'day':
            return []
        from . import config  # local import keeps engine imports flat
        events = []
        for row in self.tiles:
            for tile in row:
                if tile.crop_state != 'growing':
                    continue
                tile.crop_growth_ticks += 1
                if tile.crop_growth_ticks >= config.CROP_MATURE_TICKS:
                    tile.crop_state = 'mature'
                    tile.resource_amount = config.HARVEST_YIELD
                    events.append({
                        'type': 'crop_matured',
                        'description': f'crop matured at ({tile.x},{tile.y})',
                        'data': {
                            'tile_x': tile.x,
                            'tile_y': tile.y,
                            'colony_id': tile.crop_colony_id,
                        },
                    })
        return events
```

- [ ] **Step 4: Run test to verify it passes**

```bash
docker compose run --rm flask pytest tests/engine/test_world_tick.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/engine/world.py backend/tests/engine/test_world_tick.py
git commit -m "feat(engine): World.tick(phase) grows crops during day phase"
```

---

### Task 5: EngineColony class

**Files:**
- Create: `backend/app/engine/colony.py`
- Test: append to `backend/tests/engine/test_cycle.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/engine/test_cycle.py`:

```python
from app.engine.colony import EngineColony


def test_engine_colony_defaults_and_overrides():
    c = EngineColony(id=1, name='Red', color='#e74c3c',
                     camp_x=3, camp_y=3, food_stock=18)
    assert c.id == 1
    assert c.name == 'Red'
    assert c.color == '#e74c3c'
    assert c.camp_x == 3 and c.camp_y == 3
    assert c.food_stock == 18
    assert c.growing_count == 0   # default

def test_engine_colony_is_at_camp():
    c = EngineColony(id=1, name='Red', color='#e74c3c',
                     camp_x=3, camp_y=3, food_stock=0)
    assert c.is_at_camp(3, 3)
    assert not c.is_at_camp(4, 3)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose run --rm flask pytest tests/engine/test_cycle.py -v
```

Expected: ImportError — `colony` module doesn't exist.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/engine/colony.py
"""Pure in-engine colony representation. No Flask, no DB.

Mirrors the `colonies` ORM row shape but lives in the engine layer so
agents can read colony state (camp position, food_stock, growing_count)
without reaching through the service. Mutations (food_stock++/-- and
growing_count++/--) happen here during a step; the service persists the
deltas via dirty-colony set after the step returns.
"""


class EngineColony:
    __slots__ = ('id', 'name', 'color', 'camp_x', 'camp_y',
                 'food_stock', 'growing_count')

    def __init__(self, id, name, color, camp_x, camp_y,
                 food_stock, growing_count=0):
        self.id = id
        self.name = name
        self.color = color
        self.camp_x = camp_x
        self.camp_y = camp_y
        self.food_stock = food_stock
        self.growing_count = growing_count

    def is_at_camp(self, x, y):
        return x == self.camp_x and y == self.camp_y

    def __repr__(self):
        return f"EngineColony(#{self.id} {self.name} @({self.camp_x},{self.camp_y}))"
```

- [ ] **Step 4: Run test to verify it passes**

```bash
docker compose run --rm flask pytest tests/engine/test_cycle.py -v
```

Expected: all tests in file pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/engine/colony.py backend/tests/engine/test_cycle.py
git commit -m "feat(engine): EngineColony pure class with food_stock + growing_count"
```

---

### Task 6: Agent gains colony_id + ate_dawn flag

**Files:**
- Modify: `backend/app/engine/agent.py` (add `colony_id`, `ate_this_dawn` slots)
- Test: new file `backend/tests/engine/test_agent_slots.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/engine/test_agent_slots.py
from app.engine.agent import Agent


def test_agent_has_colony_id_and_dawn_flag():
    a = Agent(name='A', x=0, y=0, colony_id=7)
    assert a.colony_id == 7
    assert a.ate_this_dawn is False


def test_agent_colony_id_defaults_to_none():
    a = Agent(name='A', x=0, y=0)
    assert a.colony_id is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose run --rm flask pytest tests/engine/test_agent_slots.py -v
```

Expected: `__init__() got an unexpected keyword argument 'colony_id'` OR AttributeError.

- [ ] **Step 3: Write minimal implementation**

Modify `backend/app/engine/agent.py`:

```python
class Agent:
    __slots__ = (
        'id', 'name', 'x', 'y', 'state',
        'hunger', 'energy', 'social', 'health',
        'age', 'alive',
        'colony_id', 'ate_this_dawn',
    )

    def __init__(self, name, x, y, agent_id=None, colony_id=None):
        self.id = agent_id
        self.name = name
        self.x = x
        self.y = y
        self.state = actions.STATE_IDLE
        self.hunger = needs.NEED_MAX
        self.energy = needs.NEED_MAX
        self.social = needs.NEED_MAX
        self.health = needs.NEED_MAX
        self.age = 0
        self.alive = True
        self.colony_id = colony_id
        # Transient: set True when agent emits ate_from_cache in dawn phase;
        # cleared by tick_agent when phase != 'dawn'. Keeps one-meal-per-day
        # enforced without persisting a per-agent counter.
        self.ate_this_dawn = False
```

- [ ] **Step 4: Run test to verify it passes**

```bash
docker compose run --rm flask pytest tests/engine/test_agent_slots.py -v
docker compose run --rm flask pytest tests/engine -v    # sanity: no regressions
```

Expected: new 2 pass; no existing test breaks.

- [ ] **Step 5: Commit**

```bash
git add backend/app/engine/agent.py backend/tests/engine/test_agent_slots.py
git commit -m "feat(engine): Agent gains colony_id and ate_this_dawn flag"
```

---

### Task 7: Plant action

**Files:**
- Modify: `backend/app/engine/actions.py` (add `plant` function)
- Test: new file `backend/tests/engine/test_actions_plant_harvest.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/engine/test_actions_plant_harvest.py
from app.engine.agent import Agent
from app.engine.colony import EngineColony
from app.engine.world import Tile, World
from app.engine import actions, config


def _grass_world():
    w = World(5, 5)
    w.tiles = [[Tile(x, y, 'grass') for x in range(5)] for y in range(5)]
    return w


def _fresh_colony(growing=0, food=18):
    return EngineColony(id=1, name='Red', color='#e74c3c',
                        camp_x=0, camp_y=0, food_stock=food,
                        growing_count=growing)


def test_plant_converts_empty_tile_to_growing():
    w = _grass_world()
    a = Agent('A', 2, 2, agent_id=10, colony_id=1)
    c = _fresh_colony()
    event = actions.plant(a, w, c)
    tile = w.get_tile(2, 2)
    assert tile.crop_state == 'growing'
    assert tile.crop_growth_ticks == 0
    assert tile.crop_colony_id == 1
    assert c.growing_count == 1
    assert event['type'] == 'planted'
    assert event['data'] == {
        'tile_x': 2, 'tile_y': 2,
        'colony_id': 1, 'agent_id': 10,
    }


def test_plant_refuses_already_cultivated_tile():
    w = _grass_world()
    w.get_tile(2, 2).crop_state = 'growing'
    a = Agent('A', 2, 2, agent_id=10, colony_id=1)
    c = _fresh_colony(growing=1)
    event = actions.plant(a, w, c)
    # Returns a no-op idled event; state untouched; counter unchanged.
    assert event['type'] == 'idled'
    assert c.growing_count == 1


def test_plant_refuses_when_max_fields_reached():
    w = _grass_world()
    a = Agent('A', 2, 2, agent_id=10, colony_id=1)
    c = _fresh_colony(growing=config.MAX_FIELDS_PER_COLONY)
    event = actions.plant(a, w, c)
    assert event['type'] == 'idled'
    assert w.get_tile(2, 2).crop_state == 'none'
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose run --rm flask pytest tests/engine/test_actions_plant_harvest.py -v
```

Expected: AttributeError — `actions` has no `plant`.

- [ ] **Step 3: Write minimal implementation**

Add to `backend/app/engine/actions.py` (after `explore`):

```python
def plant(agent, world, colony):
    """Convert the tile under `agent` into a growing crop owned by `colony`.

    Pre-conditions (caller should already have checked via decide_action):
      * tile.crop_state == 'none'
      * tile.resource_amount == 0 (i.e. empty wild)
      * colony.growing_count < config.MAX_FIELDS_PER_COLONY

    This function re-guards all three; a violated pre-condition yields an
    `idled` no-op event so the engine never silently mutates state.
    """
    from . import config
    tile = world.get_tile(agent.x, agent.y)
    if tile.crop_state != 'none':
        return {'type': 'idled', 'description': f'{agent.name} found crop already here'}
    if tile.resource_amount > 0:
        return {'type': 'idled', 'description': f'{agent.name} found wild food here, skipping plant'}
    if colony.growing_count >= config.MAX_FIELDS_PER_COLONY:
        return {'type': 'idled', 'description': f'{agent.name} deferred plant (field cap)'}

    tile.crop_state = 'growing'
    tile.crop_growth_ticks = 0
    tile.crop_colony_id = colony.id
    colony.growing_count += 1
    return {
        'type': 'planted',
        'description': f'{agent.name} planted at ({tile.x},{tile.y})',
        'data': {
            'tile_x': tile.x,
            'tile_y': tile.y,
            'colony_id': colony.id,
            'agent_id': agent.id,
        },
    }
```

- [ ] **Step 4: Run test to verify it passes**

```bash
docker compose run --rm flask pytest tests/engine/test_actions_plant_harvest.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/engine/actions.py backend/tests/engine/test_actions_plant_harvest.py
git commit -m "feat(engine): plant action for day-phase cultivation"
```

---

### Task 8: Harvest action

**Files:**
- Modify: `backend/app/engine/actions.py` (add `harvest`)
- Test: append to `backend/tests/engine/test_actions_plant_harvest.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/engine/test_actions_plant_harvest.py`:

```python
def test_harvest_credits_harvester_colony_and_resets_tile():
    w = _grass_world()
    t = w.get_tile(2, 2)
    t.crop_state = 'mature'
    t.crop_growth_ticks = config.CROP_MATURE_TICKS
    t.resource_amount = config.HARVEST_YIELD
    t.crop_colony_id = 99  # planter colony id, *different* from harvester

    a = Agent('A', 2, 2, agent_id=10, colony_id=1)
    harvester = _fresh_colony()  # id=1
    event = actions.harvest(a, w, harvester)

    assert event['type'] == 'harvested'
    assert event['data'] == {
        'tile_x': 2, 'tile_y': 2,
        'colony_id': 1,                             # harvester
        'agent_id': 10,
        'yield_amount': config.HARVEST_YIELD,
    }
    assert harvester.food_stock == 18 + config.HARVEST_YIELD
    # Tile back to wild-empty.
    assert t.crop_state == 'none'
    assert t.crop_growth_ticks == 0
    assert t.crop_colony_id is None
    assert t.resource_amount == 0


def test_harvest_refuses_non_mature_tile():
    w = _grass_world()
    w.get_tile(2, 2).crop_state = 'growing'
    a = Agent('A', 2, 2, agent_id=10, colony_id=1)
    c = _fresh_colony()
    event = actions.harvest(a, w, c)
    assert event['type'] == 'idled'
    assert c.food_stock == 18
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose run --rm flask pytest tests/engine/test_actions_plant_harvest.py -v
```

Expected: AttributeError — `actions.harvest` not defined.

- [ ] **Step 3: Write minimal implementation**

Add to `backend/app/engine/actions.py`:

```python
def harvest(agent, world, colony):
    """Harvest a mature crop under `agent`. Credits `colony` (the harvester).

    The planter's colony is NOT credited — this is the "pure scarcity, no
    ownership" rule from the spec. Any agent can harvest any mature tile
    and the yield goes to their own colony's stock.
    """
    from . import config
    tile = world.get_tile(agent.x, agent.y)
    if tile.crop_state != 'mature':
        return {'type': 'idled', 'description': f'{agent.name} found no mature crop'}

    yield_amount = config.HARVEST_YIELD
    colony.food_stock += yield_amount
    tile.crop_state = 'none'
    tile.crop_growth_ticks = 0
    tile.crop_colony_id = None
    tile.resource_amount = 0

    return {
        'type': 'harvested',
        'description': f'{agent.name} harvested ({tile.x},{tile.y}) → +{yield_amount} stock',
        'data': {
            'tile_x': tile.x,
            'tile_y': tile.y,
            'colony_id': colony.id,
            'agent_id': agent.id,
            'yield_amount': yield_amount,
        },
    }
```

- [ ] **Step 4: Run test to verify it passes**

```bash
docker compose run --rm flask pytest tests/engine/test_actions_plant_harvest.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/engine/actions.py backend/tests/engine/test_actions_plant_harvest.py
git commit -m "feat(engine): harvest action credits harvester colony + resets tile"
```

---

### Task 9: Eat-at-camp action (dawn)

**Files:**
- Modify: `backend/app/engine/actions.py` (add `eat_camp`)
- Test: new file `backend/tests/engine/test_dawn_eat.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/engine/test_dawn_eat.py
from app.engine.agent import Agent
from app.engine.colony import EngineColony
from app.engine.world import World, Tile
from app.engine import actions, config, needs


def _camp_world():
    w = World(5, 5)
    w.tiles = [[Tile(x, y, 'grass') for x in range(5)] for y in range(5)]
    return w


def _colony_at_camp(food_stock=config.INITIAL_FOOD_STOCK):
    return EngineColony(id=1, name='Red', color='#e74c3c',
                        camp_x=1, camp_y=1, food_stock=food_stock)


def test_eat_camp_requires_agent_at_camp():
    w = _camp_world()
    c = _colony_at_camp()
    a = Agent('A', 2, 2, agent_id=1, colony_id=1)
    a.hunger = 50.0
    event = actions.eat_camp(a, c)
    assert event['type'] == 'idled'
    assert c.food_stock == config.INITIAL_FOOD_STOCK
    assert a.hunger == 50.0


def test_eat_camp_requires_sufficient_stock():
    w = _camp_world()
    c = _colony_at_camp(food_stock=config.EAT_COST - 1)
    a = Agent('A', 1, 1, agent_id=1, colony_id=1)
    a.hunger = 50.0
    event = actions.eat_camp(a, c)
    assert event['type'] == 'idled'
    assert a.hunger == 50.0


def test_eat_camp_skipped_when_already_full():
    c = _colony_at_camp()
    a = Agent('A', 1, 1, agent_id=1, colony_id=1)
    a.hunger = needs.NEED_MAX  # already full
    event = actions.eat_camp(a, c)
    assert event['type'] == 'idled'
    assert c.food_stock == config.INITIAL_FOOD_STOCK


def test_eat_camp_cap_fills_hunger_and_debits_stock():
    c = _colony_at_camp()
    a = Agent('A', 1, 1, agent_id=1, colony_id=1)
    a.hunger = 45.0
    event = actions.eat_camp(a, c)
    assert event['type'] == 'ate_from_cache'
    assert event['data']['amount'] == config.EAT_COST
    assert event['data']['colony_id'] == 1
    assert event['data']['hunger_before'] == 45.0
    assert event['data']['hunger_after'] == needs.NEED_MAX
    assert a.hunger == needs.NEED_MAX
    assert c.food_stock == config.INITIAL_FOOD_STOCK - config.EAT_COST
    assert a.ate_this_dawn is True


def test_eat_camp_refuses_second_meal_same_dawn():
    c = _colony_at_camp()
    a = Agent('A', 1, 1, agent_id=1, colony_id=1)
    a.hunger = 45.0
    actions.eat_camp(a, c)  # first meal
    # Fake a further hunger drop; agent is still flagged as ate_this_dawn.
    a.hunger = 50.0
    event = actions.eat_camp(a, c)
    assert event['type'] == 'idled'
    assert c.food_stock == config.INITIAL_FOOD_STOCK - config.EAT_COST   # only one debit
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose run --rm flask pytest tests/engine/test_dawn_eat.py -v
```

Expected: AttributeError — `actions.eat_camp` not defined.

- [ ] **Step 3: Write minimal implementation**

Add to `backend/app/engine/actions.py`:

```python
def eat_camp(agent, colony):
    """Dawn meal at camp. Cap-fills hunger, debits colony stock by EAT_COST.

    Pre-conditions:
      * agent on own camp tile
      * colony.food_stock >= EAT_COST
      * agent.hunger < NEED_MAX
      * agent has not already eaten this dawn window

    Violations → idled no-op. Success → cap-fills hunger, emits
    ate_from_cache with amount=EAT_COST, flags agent.ate_this_dawn.
    """
    from . import config
    if not colony.is_at_camp(agent.x, agent.y):
        return {'type': 'idled', 'description': f'{agent.name} not at camp'}
    if colony.food_stock < config.EAT_COST:
        return {'type': 'idled', 'description': f'{agent.name} found empty stock'}
    if agent.hunger >= needs.NEED_MAX:
        return {'type': 'idled', 'description': f'{agent.name} already full'}
    if agent.ate_this_dawn:
        return {'type': 'idled', 'description': f'{agent.name} already ate this dawn'}

    hunger_before = agent.hunger
    agent.hunger = needs.NEED_MAX
    colony.food_stock -= config.EAT_COST
    agent.ate_this_dawn = True
    return {
        'type': 'ate_from_cache',
        'description': f'{agent.name} ate at camp',
        'data': {
            'agent_id': agent.id,
            'colony_id': colony.id,
            'amount': config.EAT_COST,
            'hunger_before': hunger_before,
            'hunger_after': agent.hunger,
        },
    }
```

- [ ] **Step 4: Run test to verify it passes**

```bash
docker compose run --rm flask pytest tests/engine/test_dawn_eat.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/engine/actions.py backend/tests/engine/test_dawn_eat.py
git commit -m "feat(engine): eat_camp action (dawn meal, cap-fill, once-per-dawn)"
```

---

### Task 10: Extend decide_action with phase + colony

**Files:**
- Modify: `backend/app/engine/agent.py` (`decide_action`, `execute_action`, `tick_agent` signatures)
- Test: new file `backend/tests/engine/test_decide_action_phase.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/engine/test_decide_action_phase.py
from app.engine.agent import Agent, decide_action
from app.engine.colony import EngineColony
from app.engine.world import Tile, World
from app.engine import config, needs


def _grass_world():
    w = World(5, 5)
    w.tiles = [[Tile(x, y, 'grass') for x in range(5)] for y in range(5)]
    return w


def _colony(growing=0):
    return EngineColony(id=1, name='Red', color='#e74c3c',
                        camp_x=0, camp_y=0, food_stock=18,
                        growing_count=growing)


def _fresh_agent(x=2, y=2):
    a = Agent('A', x, y, agent_id=1, colony_id=1)
    # Neutral needs: not hungry, not tired, not lonely.
    a.hunger = 80.0
    a.energy = 80.0
    a.social = 80.0
    a.health = 80.0
    return a


def test_day_phase_harvest_wins_over_plant_when_on_mature_tile():
    w = _grass_world()
    w.get_tile(2, 2).crop_state = 'mature'
    a = _fresh_agent()
    assert decide_action(a, w, _colony(), 'day') == 'harvest'


def test_day_phase_plant_chosen_on_empty_tile():
    w = _grass_world()
    a = _fresh_agent()
    assert decide_action(a, w, _colony(), 'day') == 'plant'


def test_day_phase_growing_tile_skips_both():
    w = _grass_world()
    w.get_tile(2, 2).crop_state = 'growing'
    a = _fresh_agent()
    # Falls through to existing social/explore chain.
    action = decide_action(a, w, _colony(), 'day')
    assert action in ('socialise', 'explore')


def test_hunger_critical_overrides_day_productive():
    w = _grass_world()
    a = _fresh_agent()
    a.hunger = needs.HUNGER_CRITICAL - 1
    assert decide_action(a, w, _colony(), 'day') == 'forage'


def test_max_fields_closes_plant_path():
    w = _grass_world()
    a = _fresh_agent()
    c = _colony(growing=config.MAX_FIELDS_PER_COLONY)
    # Empty tile + cap reached → falls through productive branch.
    action = decide_action(a, w, c, 'day')
    assert action != 'plant'


def test_dawn_phase_on_camp_returns_eat_when_hungry_and_stock():
    w = _grass_world()
    a = _fresh_agent(x=0, y=0)
    a.hunger = 60.0
    c = _colony()   # camp at 0,0
    assert decide_action(a, w, c, 'dawn') == 'eat_camp'


def test_dawn_phase_off_camp_steps_toward_camp():
    w = _grass_world()
    a = _fresh_agent(x=2, y=2)
    c = _colony()
    assert decide_action(a, w, c, 'dawn') == 'step_to_camp'


def test_dusk_phase_always_steps_toward_camp():
    w = _grass_world()
    a = _fresh_agent(x=2, y=2)
    assert decide_action(a, w, _colony(), 'dusk') == 'step_to_camp'


def test_night_phase_returns_rest():
    w = _grass_world()
    a = _fresh_agent()
    assert decide_action(a, w, _colony(), 'night') == 'rest'
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose run --rm flask pytest tests/engine/test_decide_action_phase.py -v
```

Expected: `decide_action()` signature rejects new args, or returns wrong action.

- [ ] **Step 3: Write minimal implementation**

Replace `decide_action` and `execute_action` in `backend/app/engine/agent.py`:

```python
def decide_action(agent, world, colony, phase):
    """Return the name of the action this agent should take this tick.

    Order of precedence:
      1. Survival (health/hunger/energy crit) — always applies.
      2. Phase gating:
         - dawn: eat at camp if possible, else walk there
         - dusk: walk to camp
         - night: rest (engine-wide; hunger decay halved in tick_agent)
         - day: extended productive chain (harvest > plant > ...)
      3. Existing tail (hunger_mod forage → social → explore).

    Pure — same inputs yield same output.
    """
    from . import config

    # Survival takes precedence over any phase behavior.
    if agent.health < needs.HEALTH_CRITICAL:
        return 'rest' if agent.energy < needs.ENERGY_CRITICAL else 'forage'
    if agent.hunger < needs.HUNGER_CRITICAL:
        return 'forage'
    if agent.energy < needs.ENERGY_CRITICAL:
        return 'rest'

    if phase == 'night':
        return 'rest'
    if phase == 'dusk':
        return 'step_to_camp'
    if phase == 'dawn':
        if colony.is_at_camp(agent.x, agent.y) \
           and agent.hunger < needs.NEED_MAX \
           and colony.food_stock >= config.EAT_COST \
           and not agent.ate_this_dawn:
            return 'eat_camp'
        return 'step_to_camp'

    # phase == 'day' — productive branches
    tile = world.get_tile(agent.x, agent.y)
    if tile.crop_state == 'mature':
        return 'harvest'
    if tile.crop_state == 'none' and tile.resource_amount == 0 \
       and colony.growing_count < config.MAX_FIELDS_PER_COLONY:
        return 'plant'

    # existing hunger/social/explore fallthrough
    if agent.hunger < needs.HUNGER_MODERATE:
        return 'forage'
    if agent.social < needs.SOCIAL_LOW:
        return 'socialise'
    return 'explore'


def execute_action(action_name, agent, world, all_agents, colony, *, rng):
    if action_name == 'forage':
        return actions.forage(agent, world, rng=rng)
    if action_name == 'rest':
        return actions.rest(agent)
    if action_name == 'socialise':
        return actions.socialise(agent, all_agents)
    if action_name == 'explore':
        return actions.explore(agent, world, rng=rng)
    if action_name == 'plant':
        return actions.plant(agent, world, colony)
    if action_name == 'harvest':
        return actions.harvest(agent, world, colony)
    if action_name == 'eat_camp':
        return actions.eat_camp(agent, colony)
    if action_name == 'step_to_camp':
        moved = actions.step_toward(agent, colony.camp_x, colony.camp_y, world)
        return {
            'type': 'moved' if moved else 'idled',
            'description': f'{agent.name} headed toward camp',
        }
    return {'type': 'idled', 'description': f'{agent.name} did nothing'}
```

Don't update `tick_agent` yet — Task 12 handles that.

- [ ] **Step 4: Run test to verify it passes**

```bash
docker compose run --rm flask pytest tests/engine/test_decide_action_phase.py -v
```

Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/engine/agent.py backend/tests/engine/test_decide_action_phase.py
git commit -m "feat(engine): decide_action gains phase + colony; plant/harvest/eat branches"
```

---

### Task 11: Tick_agent + night hunger scaling + dawn-flag reset

**Files:**
- Modify: `backend/app/engine/agent.py` (`tick_agent`), `backend/app/engine/needs.py` (decay_needs accepts phase scaling)
- Test: new file `backend/tests/engine/test_night_decay.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/engine/test_night_decay.py
from app.engine.agent import Agent, tick_agent
from app.engine.colony import EngineColony
from app.engine.world import Tile, World
from app.engine import needs
import random


def _world():
    w = World(5, 5)
    w.tiles = [[Tile(x, y, 'grass') for x in range(5)] for y in range(5)]
    return w


def _colony(): return EngineColony(1, 'R', '#000', camp_x=0, camp_y=0, food_stock=18)


def test_night_phase_hunger_decays_at_half_rate():
    a_day = Agent('A', 2, 2, agent_id=1, colony_id=1)
    a_night = Agent('B', 2, 2, agent_id=2, colony_id=1)
    a_day.hunger = a_night.hunger = 80.0
    w = _world()
    rng = random.Random(1)
    tick_agent(a_day, w, [a_day], {1: _colony()}, phase='day', rng=rng)
    tick_agent(a_night, w, [a_night], {1: _colony()}, phase='night', rng=rng)
    day_delta = 80.0 - a_day.hunger
    night_delta = 80.0 - a_night.hunger
    assert night_delta == day_delta * needs.NIGHT_HUNGER_SCALE


def test_ate_this_dawn_flag_clears_outside_dawn():
    a = Agent('A', 0, 0, agent_id=1, colony_id=1)
    a.ate_this_dawn = True
    w = _world()
    rng = random.Random(1)
    tick_agent(a, w, [a], {1: _colony()}, phase='day', rng=rng)
    assert a.ate_this_dawn is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose run --rm flask pytest tests/engine/test_night_decay.py -v
```

Expected: `tick_agent` signature rejects `colonies` and `phase` args.

- [ ] **Step 3: Write minimal implementation**

Modify `tick_agent` in `backend/app/engine/agent.py`:

```python
def tick_agent(agent, world, all_agents, colonies_by_id, *, phase, rng):
    """Advance one tick for `agent`.

    `colonies_by_id` is a dict {colony_id: EngineColony}. Indexing by
    agent.colony_id keeps lookup O(1). `phase` comes from cycle.phase_for.
    """
    if not agent.alive:
        return []

    events = []

    if agent.health <= 0:
        events.append(actions.die(agent))
        return events

    # Dawn-eat flag is transient: cleared any tick that isn't in the dawn
    # window so next dawn's decide_action sees a fresh eligibility.
    if phase != 'dawn':
        agent.ate_this_dawn = False

    # Hunger decay scales down at night (agents are asleep).
    scale = needs.NIGHT_HUNGER_SCALE if phase == 'night' else 1.0
    needs.decay_needs(agent, hunger_scale=scale)

    if agent.health <= 0:
        events.append(actions.die(agent))
        return events

    colony = colonies_by_id.get(agent.colony_id)
    action_name = decide_action(agent, world, colony, phase)
    events.append(execute_action(action_name, agent, world, all_agents, colony, rng=rng))

    agent.age += 1
    return events
```

Modify `decay_needs` in `backend/app/engine/needs.py`:

```python
def decay_needs(agent, hunger_scale=1.0):
    agent.hunger = max(0.0, agent.hunger - HUNGER_DECAY * hunger_scale)
    agent.energy = max(0.0, agent.energy - ENERGY_DECAY)
    agent.social = max(0.0, agent.social - SOCIAL_DECAY)
    if agent.hunger <= 0.0:
        agent.health = max(0.0, agent.health - STARVATION_HEALTH_DAMAGE)
    elif agent.hunger > HUNGER_MODERATE:
        agent.health = min(NEED_MAX, agent.health + PASSIVE_HEAL_RATE)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
docker compose run --rm flask pytest tests/engine/test_night_decay.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/engine/agent.py backend/app/engine/needs.py backend/tests/engine/test_night_decay.py
git commit -m "feat(engine): tick_agent threads phase + colony; night halves hunger decay"
```

---

### Task 12: Simulation.step wires cycle + colonies

**Files:**
- Modify: `backend/app/engine/simulation.py` (`Simulation.__init__`, `step`, `new_simulation`)
- Test: new file `backend/tests/engine/test_dusk_pathing.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/engine/test_dusk_pathing.py
from app.engine.simulation import new_simulation
from app.engine.colony import EngineColony
from app.engine import cycle


def test_simulation_emits_crop_matured_during_day_phase():
    # Build a sim with 1 agent, 1 colony, force one tile to growing.
    sim = new_simulation(
        width=5, height=5, seed=42,
        colonies=[EngineColony(1, 'R', '#000', camp_x=0, camp_y=0, food_stock=18)],
        agents_per_colony=0,   # skip agent spawning to keep the test isolated
    )
    # Guarantee at least one grass tile to plant on.
    t = None
    for row in sim.world.tiles:
        for tile in row:
            if tile.terrain == 'grass':
                t = tile
                t.terrain = 'grass'
                t.crop_state = 'growing'
                t.crop_growth_ticks = 59
                t.crop_colony_id = 1
                break
        if t: break
    assert t is not None

    # Advance until we hit a day-phase tick.
    while cycle.phase_for(sim.current_tick) != 'day':
        sim.step()
    events = sim.step()
    assert t.crop_state == 'mature'
    assert any(e['type'] == 'crop_matured' for e in events)


def test_simulation_dusk_phase_steps_agent_toward_camp():
    sim = new_simulation(
        width=5, height=5, seed=1,
        colonies=[EngineColony(1, 'R', '#000', camp_x=0, camp_y=0, food_stock=18)],
        agents_per_colony=1,
    )
    agent = sim.agents[0]
    agent.x, agent.y = 4, 4
    agent.colony_id = 1

    # Warp sim to the start of dusk (tick 60) without touching RNG behavior.
    sim.current_tick = 60
    sim.step()
    # One Manhattan step toward (0,0) should have landed.
    assert (agent.x, agent.y) != (4, 4)
    assert abs(agent.x - 0) + abs(agent.y - 0) <= 7   # reduced by 1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose run --rm flask pytest tests/engine/test_dusk_pathing.py -v
```

Expected: `new_simulation()` rejects `colonies=...` kwarg, OR tick_agent call in step has wrong signature.

- [ ] **Step 3: Write minimal implementation**

Replace `Simulation.step` and `new_simulation` in `backend/app/engine/simulation.py`:

```python
from .agent import Agent, tick_agent
from .world import World
from . import cycle


class Simulation:
    def __init__(self, world, agents=None, current_tick=0, seed=None, colonies=None):
        self.world = world
        self.agents = list(agents) if agents is not None else []
        self.current_tick = current_tick
        self.seed = seed
        self.rng_spawn = random.Random(_sub_seed(seed, 'spawn'))
        self.rng_tick = random.Random(_sub_seed(seed, 'tick'))
        # {colony_id: EngineColony}. Empty dict for legacy sims (pre-colony).
        self.colonies = {c.id: c for c in (colonies or [])}

    # snapshot_rng_state, restore_rng_state, alive_agents, add_agent,
    # spawn_agent unchanged.

    def step(self):
        events = []
        phase = cycle.phase_for(self.current_tick)
        # Refresh `colony.growing_count` from tiles at the top of every step.
        # Spec contract: the counter is authoritative at step boundaries and
        # mutable within a step. `plant` bumps the counter locally so later
        # agents in the same tick see the fresh value and respect the field
        # cap. `harvest` never touches the counter — the next step's
        # recompute closes the loop. See spec §"Cultivation state ownership".
        self._recompute_growing_counts()
        snapshot = list(self.agents)
        for agent in snapshot:
            if not agent.alive:
                continue
            for event in tick_agent(
                agent, self.world, snapshot, self.colonies,
                phase=phase, rng=self.rng_tick,
            ):
                event['tick'] = self.current_tick
                event['agent_id'] = agent.id
                events.append(event)

        # World-level tick: crop growth during day phase, etc.
        for event in self.world.tick(phase):
            event['tick'] = self.current_tick
            events.append(event)

        self.current_tick += 1
        return events

    def _recompute_growing_counts(self):
        """Re-derive `colony.growing_count` from tile state.

        Called at the start of each `step`. Stale counters (e.g. after
        harvest freed a tile in the prior tick) are corrected here rather
        than in `harvest`, which would otherwise need a colony handle it
        doesn't have. Cost is O(tiles) per tick — acceptable for demo-scale
        grids (≤10k cells).
        """
        counts = {cid: 0 for cid in self.colonies}
        for row in self.world.tiles:
            for tile in row:
                if tile.crop_state == 'growing' and tile.crop_colony_id in counts:
                    counts[tile.crop_colony_id] += 1
        for cid, colony in self.colonies.items():
            colony.growing_count = counts[cid]
```

Update `new_simulation` signature:

```python
def new_simulation(width, height, seed=None, agent_count=0, agent_name_prefix='Agent',
                   colonies=None, agents_per_colony=None):
    """Build a fresh sim.

    Legacy path: pass `agent_count` to spawn N un-affiliated agents (used
    by pre-cultivation tests and audit scripts).

    Colonies path: pass `colonies=[EngineColony...]` and `agents_per_colony`
    to spawn a team of agents per colony at each camp tile. Ignores
    `agent_count` when either is set.
    """
    # existing int validation on width/height/agent_count unchanged ...

    world = World(width, height)
    world.generate(seed=seed)
    sim = Simulation(world, seed=seed, colonies=colonies)

    if colonies is not None and agents_per_colony is not None:
        for colony in colonies:
            for i in range(agents_per_colony):
                name = f'{colony.name}-{i + 1}'
                # Spawn directly at camp tile (must be walkable or this is
                # a caller bug — camps are chosen by create_simulation on
                # known walkable coords).
                a = Agent(name, colony.camp_x, colony.camp_y, colony_id=colony.id)
                sim.agents.append(a)
    else:
        for i in range(agent_count):
            sim.spawn_agent(f'{agent_name_prefix}-{i + 1}')
    return sim
```

- [ ] **Step 4: Run test to verify it passes**

```bash
docker compose run --rm flask pytest tests/engine/test_dusk_pathing.py -v
docker compose run --rm flask pytest tests/engine -v       # no regressions
```

Expected: new 2 pass; existing engine tests still green.

**Caveat — existing legacy tests:** some pass `colonies=None` via the default path. Their `tick_agent` will see `colonies_by_id={}` and `colony=None` from `.get()`. `decide_action` must handle `colony is None` gracefully for those tests — add a guard at the top:

```python
def decide_action(agent, world, colony, phase):
    if colony is None:
        # Legacy path (no-colony sim). Fall back to the original chain.
        return _legacy_decide_action(agent)
    ...


def _legacy_decide_action(agent):
    if agent.health < needs.HEALTH_CRITICAL:
        return 'rest' if agent.energy < needs.ENERGY_CRITICAL else 'forage'
    if agent.hunger < needs.HUNGER_CRITICAL:
        return 'forage'
    if agent.energy < needs.ENERGY_CRITICAL:
        return 'rest'
    if agent.hunger < needs.HUNGER_MODERATE:
        return 'forage'
    if agent.social < needs.SOCIAL_LOW:
        return 'socialise'
    return 'explore'
```

If existing service/route tests fail here, this fallback is why.

- [ ] **Step 5: Commit**

```bash
git add backend/app/engine/simulation.py backend/app/engine/agent.py backend/tests/engine/test_dusk_pathing.py
git commit -m "feat(engine): Simulation wires cycle phase + colonies into tick loop"
```

---

# Phase 1 — ORM + migration

### Task 13: Colony ORM model

**Files:**
- Create: `backend/app/models/colony.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/services/test_simulation_service.py — append at bottom
from app import models


def test_colony_model_imports_and_has_expected_columns(db_session):
    c = models.Colony(name='Red', color='#e74c3c', camp_x=3, camp_y=3, food_stock=18)
    db.session.add(c)
    db.session.flush()
    assert c.id is not None
    assert c.name == 'Red'
    assert c.food_stock == 18
```

(Add `from app import db` import at top if not already imported.)

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose run --rm flask pytest tests/services/test_simulation_service.py::test_colony_model_imports_and_has_expected_columns -v
```

Expected: ImportError or AttributeError — `models.Colony` doesn't exist.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/models/colony.py
from app import db


class Colony(db.Model):
    __tablename__ = 'colonies'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    color = db.Column(db.String(7), nullable=False)     # '#rrggbb'
    camp_x = db.Column(db.Integer, nullable=False)
    camp_y = db.Column(db.Integer, nullable=False)
    food_stock = db.Column(
        db.Integer, nullable=False, default=0, server_default='0',
    )
```

Update `backend/app/models/__init__.py`:

```python
from .simulation_state import SimulationState
from .colony import Colony
from .agent import Agent
from .world import WorldTile
from .event import Event
```

*(Do not run the test yet — migration is Task 16; the table doesn't exist in the DB.)*

- [ ] **Step 4: Commit (skip test run; covered after migration)**

```bash
git add backend/app/models/colony.py backend/app/models/__init__.py
git commit -m "feat(models): Colony ORM model"
```

---

### Task 14: Agent model gains colony_id FK

**Files:**
- Modify: `backend/app/models/agent.py`

- [ ] **Step 1 (no test — model schema, covered by migration+service tests)**

- [ ] **Step 2: Edit**

Add `colony_id` column after `alive`:

```python
    colony_id = db.Column(
        db.Integer,
        db.ForeignKey('colonies.id', ondelete='SET NULL'),
        nullable=True,
    )
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/agent.py
git commit -m "feat(models): Agent gains colony_id FK (nullable)"
```

---

### Task 15: WorldTile model gains crop columns

**Files:**
- Modify: `backend/app/models/world.py`

- [ ] **Step 1 (no test — covered by migration+service tests)**

- [ ] **Step 2: Edit**

```python
from app import db


class WorldTile(db.Model):
    __tablename__ = 'world_tiles'

    id = db.Column(db.Integer, primary_key=True)
    x = db.Column(db.Integer, nullable=False)
    y = db.Column(db.Integer, nullable=False)
    terrain = db.Column(db.String(20), nullable=False)
    resource_type = db.Column(db.String(20), nullable=True)
    resource_amount = db.Column(db.Float, default=0.0, server_default='0.0')

    crop_state = db.Column(
        db.String(10), nullable=False,
        default='none', server_default='none',
    )
    crop_growth_ticks = db.Column(
        db.Integer, nullable=False,
        default=0, server_default='0',
    )
    crop_colony_id = db.Column(
        db.Integer,
        db.ForeignKey('colonies.id', ondelete='SET NULL'),
        nullable=True,
    )

    __table_args__ = (
        db.UniqueConstraint('x', 'y', name='uq_world_tiles_xy'),
        db.Index(
            'idx_tiles_resource',
            'resource_type',
            postgresql_where=db.text('resource_type IS NOT NULL'),
        ),
        db.Index(
            'idx_tiles_crop_state',
            'crop_state',
            postgresql_where=db.text("crop_state != 'none'"),
        ),
    )
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/world.py
git commit -m "feat(models): WorldTile gains crop_state, crop_growth_ticks, crop_colony_id"
```

---

### Task 16: Alembic migration

**Files:**
- Create: `backend/migrations/versions/d4e5f6a7b8c9_colonies_crops.py`

- [ ] **Step 1: Write migration file**

```python
# backend/migrations/versions/d4e5f6a7b8c9_colonies_crops.py
"""colonies table + crop columns on world_tiles + colony_id FK on agents

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-04-15 00:00:00.000000

All schema additions are additive. The one intentional destructive step
is `DELETE FROM agents` and `DELETE FROM world_tiles` in upgrade(): the
nullable colony_id FK would otherwise leave pre-existing agent rows with
NULL and break the frontend sprite tint lookup. This is a dev-only project
(pre-demo, no production data), so a wipe is safe and avoids a two-step
nullable → backfill → NOT NULL migration.
"""
from alembic import op
import sqlalchemy as sa


revision = 'd4e5f6a7b8c9'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'colonies',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(50), nullable=False),
        sa.Column('color', sa.String(7), nullable=False),
        sa.Column('camp_x', sa.Integer(), nullable=False),
        sa.Column('camp_y', sa.Integer(), nullable=False),
        sa.Column('food_stock', sa.Integer(), nullable=False, server_default='0'),
    )

    # Dev-only wipe: remove any pre-cultivation state so the new FK + crop
    # columns start from a consistent base. Events rows can stay (they
    # don't FK into agents/world_tiles via structural constraints).
    op.execute('DELETE FROM events')
    op.execute('DELETE FROM agents')
    op.execute('DELETE FROM world_tiles')
    op.execute('DELETE FROM simulation_state')

    op.add_column('agents', sa.Column(
        'colony_id', sa.Integer(),
        sa.ForeignKey('colonies.id', ondelete='SET NULL'),
        nullable=True,
    ))

    op.add_column('world_tiles', sa.Column(
        'crop_state', sa.String(10), nullable=False, server_default='none',
    ))
    op.add_column('world_tiles', sa.Column(
        'crop_growth_ticks', sa.Integer(), nullable=False, server_default='0',
    ))
    op.add_column('world_tiles', sa.Column(
        'crop_colony_id', sa.Integer(),
        sa.ForeignKey('colonies.id', ondelete='SET NULL'),
        nullable=True,
    ))

    op.create_index(
        'idx_tiles_crop_state', 'world_tiles', ['crop_state'],
        postgresql_where=sa.text("crop_state != 'none'"),
    )


def downgrade():
    op.drop_index('idx_tiles_crop_state', table_name='world_tiles')
    op.drop_column('world_tiles', 'crop_colony_id')
    op.drop_column('world_tiles', 'crop_growth_ticks')
    op.drop_column('world_tiles', 'crop_state')
    op.drop_column('agents', 'colony_id')
    op.drop_table('colonies')
```

- [ ] **Step 2: Apply migration to clean DB**

```bash
docker compose down -v                        # destroy volume
docker compose up -d db                       # fresh postgres
docker compose run --rm flask flask db upgrade
```

Expected: two migrations applied (baseline + c3d4..b8, then new d4e5..c9). No errors.

- [ ] **Step 3: Run previously deferred Colony model test**

```bash
docker compose run --rm flask pytest tests/services/test_simulation_service.py::test_colony_model_imports_and_has_expected_columns -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/migrations/versions/d4e5f6a7b8c9_colonies_crops.py
git commit -m "feat(db): migration for colonies table + crop cols + colony_id FK"
```

---

# Phase 2 — Service layer

### Task 17: Multi-colony mappers

**Files:**
- Modify: `backend/app/services/mappers.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/services/test_simulation_service.py`:

```python
from app.engine.colony import EngineColony
from app.engine.world import Tile


def test_colony_to_row_and_back_round_trip():
    ec = EngineColony(id=None, name='Red', color='#e74c3c',
                      camp_x=3, camp_y=3, food_stock=18)
    row = mappers.colony_to_row(ec)
    assert row.name == 'Red'
    assert row.food_stock == 18
    # round-trip
    restored = mappers.row_to_colony(row)
    assert restored.name == ec.name
    assert restored.camp_x == ec.camp_x
    assert restored.food_stock == ec.food_stock


def test_tile_mapping_preserves_crop_fields():
    t = Tile(x=1, y=2, terrain='grass',
             crop_state='growing', crop_growth_ticks=15, crop_colony_id=7)
    row = mappers.tile_to_row(t)
    assert row.crop_state == 'growing'
    assert row.crop_growth_ticks == 15
    assert row.crop_colony_id == 7
    back = mappers.row_to_tile(row)
    assert back.crop_state == 'growing'
    assert back.crop_colony_id == 7


def test_agent_mapping_preserves_colony_id():
    from app.engine.agent import Agent
    a = Agent('A', 0, 0, agent_id=None, colony_id=3)
    row = mappers.agent_to_row(a)
    assert row.colony_id == 3
    back = mappers.row_to_agent(row)
    assert back.colony_id == 3
```

- [ ] **Step 2: Run to verify fails**

```bash
docker compose run --rm flask pytest tests/services/test_simulation_service.py -v -k "colony_to_row or tile_mapping or agent_mapping_preserves"
```

Expected: `mappers.colony_to_row` missing; `tile_to_row` drops new fields.

- [ ] **Step 3: Edit mappers**

Update `backend/app/services/mappers.py`:

```python
def agent_to_row(agent):
    return models.Agent(
        id=agent.id,
        name=agent.name,
        x=agent.x, y=agent.y,
        state=agent.state,
        hunger=agent.hunger, energy=agent.energy,
        social=agent.social, health=agent.health,
        age=agent.age, alive=agent.alive,
        colony_id=agent.colony_id,
    )


def row_to_agent(row):
    a = EngineAgent(name=row.name, x=row.x, y=row.y,
                    agent_id=row.id, colony_id=row.colony_id)
    a.state = row.state
    a.hunger = row.hunger
    a.energy = row.energy
    a.social = row.social
    a.health = row.health
    a.age = row.age
    a.alive = row.alive
    return a


def update_agent_row(row, engine_agent):
    row.x = engine_agent.x
    row.y = engine_agent.y
    row.state = engine_agent.state
    row.hunger = engine_agent.hunger
    row.energy = engine_agent.energy
    row.social = engine_agent.social
    row.health = engine_agent.health
    row.age = engine_agent.age
    row.alive = engine_agent.alive
    # colony_id immutable post-spawn; don't copy it.


def tile_to_row(tile):
    return models.WorldTile(
        x=tile.x, y=tile.y,
        terrain=tile.terrain,
        resource_type=tile.resource_type,
        resource_amount=tile.resource_amount,
        crop_state=tile.crop_state,
        crop_growth_ticks=tile.crop_growth_ticks,
        crop_colony_id=tile.crop_colony_id,
    )


def row_to_tile(row):
    return EngineTile(
        x=row.x, y=row.y,
        terrain=row.terrain,
        resource_type=row.resource_type,
        resource_amount=row.resource_amount,
        crop_state=row.crop_state,
        crop_growth_ticks=row.crop_growth_ticks,
        crop_colony_id=row.crop_colony_id,
    )


def update_tile_row(row, engine_tile):
    row.resource_amount = engine_tile.resource_amount
    row.crop_state = engine_tile.crop_state
    row.crop_growth_ticks = engine_tile.crop_growth_ticks
    row.crop_colony_id = engine_tile.crop_colony_id
```

Add colony mappers:

```python
from app.engine.colony import EngineColony


def colony_to_row(c):
    return models.Colony(
        id=c.id, name=c.name, color=c.color,
        camp_x=c.camp_x, camp_y=c.camp_y,
        food_stock=c.food_stock,
    )


def row_to_colony(row):
    return EngineColony(
        id=row.id, name=row.name, color=row.color,
        camp_x=row.camp_x, camp_y=row.camp_y,
        food_stock=row.food_stock,
    )


def update_colony_row(row, engine_colony):
    row.food_stock = engine_colony.food_stock
```

- [ ] **Step 4: Run test to verify passes**

```bash
docker compose run --rm flask pytest tests/services/test_simulation_service.py -v -k "colony_to_row or tile_mapping or agent_mapping_preserves"
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/mappers.py backend/tests/services/test_simulation_service.py
git commit -m "feat(service): mappers for Colony + crop fields + agent colony_id"
```

---

### Task 18: create_simulation spawns 4 colonies

**Files:**
- Modify: `backend/app/services/simulation_service.py`
- Modify: `backend/app/services/mappers.py` (helper if needed)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/services/test_simulation_service.py`:

```python
DEFAULT_COLONY_PALETTE = [
    ('Red',    '#e74c3c'),
    ('Blue',   '#3498db'),
    ('Green',  '#2ecc71'),
    ('Yellow', '#f1c40f'),
]


def test_create_simulation_spawns_four_colonies_at_corners(db_session):
    simulation_service.create_simulation(
        width=20, height=20, seed=1,
        colonies=4, agents_per_colony=3,
    )
    rows = db.session.query(models.Colony).order_by(models.Colony.id).all()
    assert len(rows) == 4
    # Expected corners for 20x20 inset 3.
    expected = [(3, 3), (16, 3), (3, 16), (16, 16)]
    got = [(r.camp_x, r.camp_y) for r in rows]
    assert got == expected
    # Palette matches.
    palette = [(r.name, r.color) for r in rows]
    assert palette == DEFAULT_COLONY_PALETTE
    # Initial stock is seeded.
    from app.engine import config
    for r in rows:
        assert r.food_stock == config.INITIAL_FOOD_STOCK


def test_create_simulation_distributes_agents_across_colonies(db_session):
    simulation_service.create_simulation(
        width=20, height=20, seed=1,
        colonies=4, agents_per_colony=3,
    )
    counts = dict(db.session.query(
        models.Agent.colony_id, db.func.count(models.Agent.id)
    ).group_by(models.Agent.colony_id).all())
    assert len(counts) == 4
    for _, n in counts.items():
        assert n == 3
```

- [ ] **Step 2: Run to verify fails**

```bash
docker compose run --rm flask pytest tests/services/test_simulation_service.py -v -k spawns_four_colonies
```

Expected: `create_simulation` signature rejects `colonies`/`agents_per_colony`.

- [ ] **Step 3: Implement new spawn path**

Update `backend/app/services/simulation_service.py`:

```python
from app.engine import config as engine_config
from app.engine.colony import EngineColony


DEFAULT_COLONY_PALETTE = [
    ('Red',    '#e74c3c'),
    ('Blue',   '#3498db'),
    ('Green',  '#2ecc71'),
    ('Yellow', '#f1c40f'),
]


def _default_camp_positions(width, height, n_colonies):
    """Corner camps inset 3 tiles. Supports 1..4 colonies; raises for more."""
    if n_colonies > 4:
        raise ValueError(f'colonies={n_colonies} exceeds supported 4')
    corners = [(3, 3), (width - 4, 3), (3, height - 4), (width - 4, height - 4)]
    return corners[:n_colonies]


def _build_default_colonies(width, height, n_colonies):
    positions = _default_camp_positions(width, height, n_colonies)
    palette = DEFAULT_COLONY_PALETTE[:n_colonies]
    out = []
    for (name, color), (cx, cy) in zip(palette, positions):
        out.append(EngineColony(
            id=None, name=name, color=color,
            camp_x=cx, camp_y=cy,
            food_stock=engine_config.INITIAL_FOOD_STOCK,
        ))
    return out


def create_simulation(width, height, seed=None,
                      colonies=4, agents_per_colony=3,
                      agent_count=None):
    """Create a fresh sim. Two calling paths:
      * Legacy:   agent_count=N + colonies=0 (no colony system, pre-cultivation)
      * Colonies: colonies=K + agents_per_colony=M (default demo path)
    """
    global _current_sim

    try:
        db.session.query(models.Event).delete()
        db.session.query(models.Agent).delete()
        db.session.query(models.WorldTile).delete()
        db.session.query(models.Colony).delete()
        db.session.query(models.SimulationState).delete()
        db.session.flush()

        if colonies and agents_per_colony is not None:
            engine_colonies = _build_default_colonies(width, height, colonies)
            # Persist colonies first — need IDs for agent FKs.
            colony_rows = [mappers.colony_to_row(c) for c in engine_colonies]
            db.session.add_all(colony_rows)
            db.session.flush()
            for c, row in zip(engine_colonies, colony_rows):
                c.id = row.id

            sim = new_simulation(
                width, height, seed=seed,
                colonies=engine_colonies,
                agents_per_colony=agents_per_colony,
            )
        else:
            sim = new_simulation(
                width, height, seed=seed,
                agent_count=agent_count or 0,
            )

        tile_rows = [mappers.tile_to_row(t) for row in sim.world.tiles for t in row]
        db.session.add_all(tile_rows)

        agent_rows = [mappers.agent_to_row(a) for a in sim.agents]
        db.session.add_all(agent_rows)
        db.session.flush()
        for agent, row in zip(sim.agents, agent_rows):
            agent.id = row.id

        state = models.SimulationState(
            current_tick=sim.current_tick,
            running=False, speed=1.0,
            world_width=width, world_height=height,
            seed=seed,
            **_rng_state_columns(sim),
        )
        db.session.add(state)

        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    _current_sim = sim
    return sim
```

- [ ] **Step 4: Run test to verify passes**

```bash
docker compose run --rm flask pytest tests/services/test_simulation_service.py -v -k spawns_four_colonies
docker compose run --rm flask pytest tests/services -v    # no regressions
```

Expected: 2 new pass; existing legacy sim tests still work (legacy path preserved via `colonies=0` OR `agents_per_colony=None`).

**If existing tests break** because they call `create_simulation(width=X, height=Y, seed=Z, agent_count=N)` and now default `colonies=4` is set: adjust the function default to `colonies=0` and make callers opt-in. Update tests to pass `colonies=4, agents_per_colony=3` explicitly in new cases.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/simulation_service.py backend/tests/services/test_simulation_service.py
git commit -m "feat(service): create_simulation spawns multi-colony layout at corners"
```

---

### Task 19: Event → DB wiring for new event types

**Files:**
- Modify: `backend/app/services/simulation_service.py` (`step_simulation` + helpers)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/services/test_simulation_service.py`:

```python
def test_step_simulation_persists_planted_tile_state(db_session):
    simulation_service.create_simulation(
        width=20, height=20, seed=1,
        colonies=4, agents_per_colony=3,
    )
    # Force one agent onto a known empty tile during day phase.
    sim = simulation_service.get_current_simulation()
    agent = sim.agents[0]
    # Find a grass tile with no resource near the agent.
    target = None
    for row in sim.world.tiles:
        for t in row:
            if t.terrain == 'grass' and t.resource_amount == 0 and t.crop_state == 'none':
                target = t; break
        if target: break
    assert target is not None
    agent.x, agent.y = target.x, target.y
    # Warp to start of day phase.
    sim.current_tick = 30
    from app.services import simulation_service as svc
    svc.step_simulation(ticks=1)
    # Check DB: the tile should now be 'growing'.
    row = db.session.query(models.WorldTile).filter_by(x=target.x, y=target.y).one()
    assert row.crop_state == 'growing'
    assert row.crop_colony_id == agent.colony_id


def test_step_simulation_persists_harvested_stock(db_session):
    simulation_service.create_simulation(
        width=20, height=20, seed=1,
        colonies=4, agents_per_colony=3,
    )
    sim = simulation_service.get_current_simulation()
    # Fake a ready-to-harvest tile under agent[0].
    agent = sim.agents[0]
    t = sim.world.get_tile(agent.x, agent.y)
    t.crop_state = 'mature'
    t.resource_amount = engine_config.HARVEST_YIELD
    t.crop_colony_id = 999
    sim.current_tick = 30    # day phase
    simulation_service.step_simulation(ticks=1)
    # Colony stock bumped by HARVEST_YIELD:
    c_row = db.session.query(models.Colony).filter_by(id=agent.colony_id).one()
    assert c_row.food_stock == engine_config.INITIAL_FOOD_STOCK + engine_config.HARVEST_YIELD


def test_step_simulation_persists_ate_from_cache_stock_debit(db_session):
    simulation_service.create_simulation(
        width=20, height=20, seed=1,
        colonies=4, agents_per_colony=3,
    )
    sim = simulation_service.get_current_simulation()
    # Agent at camp, hungry, dawn phase.
    agent = sim.agents[0]
    colony = sim.colonies[agent.colony_id]
    agent.x, agent.y = colony.camp_x, colony.camp_y
    agent.hunger = 50.0
    sim.current_tick = 0     # dawn
    initial_stock = colony.food_stock
    simulation_service.step_simulation(ticks=1)
    c_row = db.session.query(models.Colony).filter_by(id=colony.id).one()
    assert c_row.food_stock == initial_stock - engine_config.EAT_COST
```

- [ ] **Step 2: Run to verify fails**

```bash
docker compose run --rm flask pytest tests/services/test_simulation_service.py -v -k "persists_planted_tile or persists_harvested_stock or persists_ate_from_cache"
```

Expected: Tile crop_state stays 'none'; colony stock unchanged; — persistence logic absent.

- [ ] **Step 3: Implement event routing in step_simulation**

Replace `step_simulation` in `backend/app/services/simulation_service.py`:

```python
def step_simulation(ticks=1):
    if not isinstance(ticks, int) or ticks < 1:
        raise ValueError(f'ticks must be a positive int, got {ticks!r}')
    if ticks > MAX_TICKS_PER_STEP:
        raise ValueError(f'ticks={ticks} exceeds MAX_TICKS_PER_STEP={MAX_TICKS_PER_STEP}')
    sim = get_current_simulation()
    try:
        events = sim.run(ticks)

        event_rows = [mappers.event_to_row(e) for e in events]
        db.session.add_all(event_rows)

        # Dirty-tile set: old foraged + new planted/harvested/crop_matured.
        crop_dirty_coords = {
            (e['data']['tile_x'], e['data']['tile_y'])
            for e in events
            if e['type'] in ('foraged', 'planted', 'harvested', 'crop_matured')
            and e.get('data') and 'tile_x' in e['data']
        }
        if crop_dirty_coords:
            _update_dirty_tiles(sim, crop_dirty_coords)

        # Dirty-colony set: any colony referenced in harvest/eat events.
        dirty_colony_ids = {
            e['data']['colony_id']
            for e in events
            if e['type'] in ('harvested', 'ate_from_cache')
            and e.get('data') and 'colony_id' in e['data']
        }
        if dirty_colony_ids:
            _update_dirty_colonies(sim, dirty_colony_ids)

        _update_agents(sim)

        state = _load_state_row()
        state.current_tick = sim.current_tick
        rng_cols = _rng_state_columns(sim)
        state.rng_spawn_state = rng_cols['rng_spawn_state']
        state.rng_tick_state = rng_cols['rng_tick_state']

        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return events


def _update_dirty_colonies(sim, colony_ids):
    rows = (
        db.session.query(models.Colony)
        .filter(models.Colony.id.in_(colony_ids))
        .all()
    )
    for row in rows:
        engine = sim.colonies.get(row.id)
        if engine is not None:
            mappers.update_colony_row(row, engine)
```

- [ ] **Step 4: Run test to verify passes**

```bash
docker compose run --rm flask pytest tests/services/test_simulation_service.py -v -k "persists_planted_tile or persists_harvested_stock or persists_ate_from_cache"
docker compose run --rm flask pytest tests/services -v
```

Expected: 3 new pass; no regressions.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/simulation_service.py backend/tests/services/test_simulation_service.py
git commit -m "feat(service): persist planted/harvested/ate_from_cache event deltas"
```

---

### Task 20: load_current_simulation restores colonies

**Files:**
- Modify: `backend/app/services/simulation_service.py` (`load_current_simulation`)

- [ ] **Step 1: Write the failing test**

Append to test file:

```python
def test_load_current_simulation_restores_colonies(db_session):
    simulation_service.create_simulation(
        width=20, height=20, seed=1,
        colonies=4, agents_per_colony=3,
    )
    simulation_service.step_simulation(ticks=5)
    simulation_service._reset_cache()
    sim = simulation_service.load_current_simulation()
    assert len(sim.colonies) == 4
    # growing_count is recomputed from tiles after reload.
    for c in sim.colonies.values():
        assert c.growing_count >= 0
```

- [ ] **Step 2: Run — fails (colonies dict empty after reload)**

```bash
docker compose run --rm flask pytest tests/services/test_simulation_service.py -v -k restores_colonies
```

- [ ] **Step 3: Edit load_current_simulation**

```python
def load_current_simulation():
    state = db.session.query(models.SimulationState).one_or_none()
    if state is None:
        raise SimulationNotFoundError('no simulation has been created')

    tile_rows = db.session.query(models.WorldTile).all()
    world = mappers.rows_to_world(tile_rows, state.world_width, state.world_height)

    colony_rows = db.session.query(models.Colony).order_by(models.Colony.id).all()
    engine_colonies = [mappers.row_to_colony(r) for r in colony_rows]

    # Recompute growing_count from the tile rows we just loaded.
    by_id = {c.id: c for c in engine_colonies}
    for row in tile_rows:
        if row.crop_state == 'growing' and row.crop_colony_id in by_id:
            by_id[row.crop_colony_id].growing_count += 1

    sim = Simulation(
        world=world,
        current_tick=state.current_tick,
        seed=state.seed,
        colonies=engine_colonies,
    )

    agent_rows = db.session.query(models.Agent).all()
    for row in agent_rows:
        sim.agents.append(mappers.row_to_agent(row))

    if state.rng_spawn_state is not None and state.rng_tick_state is not None:
        sim.restore_rng_state({
            'spawn': state.rng_spawn_state,
            'tick': state.rng_tick_state,
        })

    return sim
```

- [ ] **Step 4: Run to verify passes**

```bash
docker compose run --rm flask pytest tests/services/test_simulation_service.py -v -k restores_colonies
docker compose run --rm flask pytest -q                    # full suite sanity
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/simulation_service.py backend/tests/services/test_simulation_service.py
git commit -m "feat(service): load_current_simulation rebuilds colonies + growing_count"
```

---

# Phase 3 — Route + serializer

### Task 21: Serializers expose colonies + phase/day

**Files:**
- Modify: `backend/app/routes/serializers.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/routes/test_simulation_routes.py` (use existing client fixture):

```python
def test_world_state_includes_sim_day_and_phase(client, db_session):
    client.put('/api/v1/simulation', json={
        'width': 20, 'height': 20, 'seed': 1,
        'colonies': 4, 'agents_per_colony': 3,
    })
    resp = client.get('/api/v1/world/state')
    assert resp.status_code == 200
    body = resp.get_json()
    assert 'day' in body['sim']
    assert 'phase' in body['sim']
    assert body['sim']['phase'] == 'dawn'
    assert body['sim']['day'] == 0


def test_world_state_includes_colonies_array(client, db_session):
    client.put('/api/v1/simulation', json={
        'width': 20, 'height': 20, 'seed': 1,
        'colonies': 4, 'agents_per_colony': 3,
    })
    body = client.get('/api/v1/world/state').get_json()
    assert 'colonies' in body
    assert len(body['colonies']) == 4
    c0 = body['colonies'][0]
    assert set(c0.keys()) >= {
        'id', 'name', 'color', 'camp_x', 'camp_y',
        'food_stock', 'growing_count',
    }


def test_agent_includes_colony_id(client, db_session):
    client.put('/api/v1/simulation', json={
        'width': 20, 'height': 20, 'seed': 1,
        'colonies': 4, 'agents_per_colony': 3,
    })
    body = client.get('/api/v1/world/state').get_json()
    for a in body['agents']:
        assert a['colony_id'] is not None


def test_tile_includes_crop_fields(client, db_session):
    client.put('/api/v1/simulation', json={
        'width': 20, 'height': 20, 'seed': 1,
        'colonies': 4, 'agents_per_colony': 3,
    })
    body = client.get('/api/v1/world/state').get_json()
    sample = body['world']['tiles'][0][0]
    assert 'crop_state' in sample
    assert 'crop_growth_ticks' in sample
    assert 'crop_colony_id' in sample
```

- [ ] **Step 2: Run — fails on missing keys / `colonies` param rejected by PUT validator**

```bash
docker compose run --rm flask pytest tests/routes/test_simulation_routes.py -v -k "world_state_includes or agent_includes_colony or tile_includes_crop"
```

- [ ] **Step 3: Edit serializers**

```python
# backend/app/routes/serializers.py
from app.engine import cycle


def agent_to_dict(agent):
    return {
        'id': agent.id,
        'name': agent.name,
        'x': agent.x, 'y': agent.y,
        'state': agent.state,
        'hunger': agent.hunger, 'energy': agent.energy,
        'social': agent.social, 'health': agent.health,
        'age': agent.age, 'alive': agent.alive,
        'colony_id': agent.colony_id,
    }


def tile_to_dict(tile):
    return {
        'x': tile.x, 'y': tile.y,
        'terrain': tile.terrain,
        'resource_type': tile.resource_type,
        'resource_amount': tile.resource_amount,
        'crop_state': tile.crop_state,
        'crop_growth_ticks': tile.crop_growth_ticks,
        'crop_colony_id': tile.crop_colony_id,
    }


def colony_to_dict(colony):
    return {
        'id': colony.id,
        'name': colony.name,
        'color': colony.color,
        'camp_x': colony.camp_x,
        'camp_y': colony.camp_y,
        'food_stock': colony.food_stock,
        'growing_count': colony.growing_count,
    }


def simulation_summary(sim, control):
    return {
        'tick': sim.current_tick,
        'seed': sim.seed,
        'width': sim.world.width,
        'height': sim.world.height,
        'agent_count': len(sim.agents),
        'alive_count': len(sim.alive_agents),
        'running': control['running'],
        'speed': control['speed'],
        'day': cycle.day_for(sim.current_tick),
        'phase': cycle.phase_for(sim.current_tick),
    }
```

Update `/world/state` route in `backend/app/routes/simulation.py` to include colonies:

```python
@bp.get('/world/state')
def get_world_state():
    since_tick = _query_int('since_tick', allow_none=True, min=-1)
    limit = _query_int('limit', default=DEFAULT_EVENTS_LIMIT,
                       min=1, max=MAX_EVENTS_LIMIT)
    sim = simulation_service.get_current_simulation()
    control = simulation_service.get_simulation_control()
    event_rows = simulation_service.query_events(since_tick=since_tick, limit=limit)
    return {
        'sim': serializers.simulation_summary(sim, control),
        'world': serializers.world_to_dict(sim.world),
        'agents': [serializers.agent_to_dict(a) for a in sim.agents],
        'colonies': [
            serializers.colony_to_dict(c) for c in sim.colonies.values()
        ],
        'events': [serializers.event_row_to_dict(r) for r in event_rows],
    }, 200
```

- [ ] **Step 4: Run — now passes day/phase/tile but colonies endpoint only populates if PUT accepts them (Task 22). Should skip colonies test here if so.**

```bash
docker compose run --rm flask pytest tests/routes/test_simulation_routes.py -v -k "world_state_includes or agent_includes_colony or tile_includes_crop"
```

If `colonies`/`agents_per_colony` PUT params aren't accepted yet, three tests pass and one (`world_state_includes_colonies_array`) fails — that's expected; Task 22 fixes it.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routes/serializers.py backend/app/routes/simulation.py backend/tests/routes/test_simulation_routes.py
git commit -m "feat(route): serializers expose day/phase, colonies[], crop tile fields"
```

---

### Task 22: PUT /simulation accepts colony params

**Files:**
- Modify: `backend/app/routes/simulation.py` (`replace_simulation`)

- [ ] **Step 1: Expected failing test already written in Task 21 (colonies array test).**

- [ ] **Step 2: Verify current fail**

```bash
docker compose run --rm flask pytest tests/routes/test_simulation_routes.py::test_world_state_includes_colonies_array -v
```

- [ ] **Step 3: Edit replace_simulation**

```python
@bp.put('/simulation')
def replace_simulation():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        _bad('request body must be a JSON object')

    width = _require_int(body.get('width'), 'width', min=1)
    height = _require_int(body.get('height'), 'height', min=1)
    if width * height > MAX_WORLD_CELLS:
        _bad(f'width*height={width * height} exceeds MAX_WORLD_CELLS={MAX_WORLD_CELLS}',
             field='width*height')

    seed = _require_int(body.get('seed'), 'seed',
                        min=_INT64_MIN, max=_INT64_MAX, allow_none=True)

    # New colony-path params. If omitted, fall back to legacy agent_count.
    colonies = _require_int(
        body.get('colonies'), 'colonies',
        min=0, max=4, allow_none=True,
    )
    agents_per_colony = _require_int(
        body.get('agents_per_colony'), 'agents_per_colony',
        min=0, max=10, allow_none=True,
    )
    agent_count = None
    if not colonies:
        agent_count = _require_int(
            body.get('agent_count', 0), 'agent_count',
            min=0, max=min(width * height, MAX_AGENTS),
        )

    sim = simulation_service.create_simulation(
        width=width, height=height, seed=seed,
        colonies=colonies or 0,
        agents_per_colony=agents_per_colony,
        agent_count=agent_count,
    )
    control = simulation_service.get_simulation_control()
    return serializers.simulation_summary(sim, control), 200
```

- [ ] **Step 4: Run to verify passes**

```bash
docker compose run --rm flask pytest tests/routes/test_simulation_routes.py -v
```

Expected: all extended route tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routes/simulation.py
git commit -m "feat(route): PUT /simulation accepts colonies + agents_per_colony"
```

---

# Phase 4 — Frontend

### Task 23: API types extended

**Files:**
- Modify: `frontend/src/api/types.ts`

- [ ] **Step 1: Write the failing test (tsc)**

No runtime test; `npx tsc --noEmit` is the gate. Write types, then the consuming components in later tasks will type-fail if anything is wrong.

- [ ] **Step 2: Edit types**

```typescript
// frontend/src/api/types.ts
export type Terrain = 'grass' | 'water' | 'forest' | 'stone' | 'sand';
export type ResourceType = 'food' | 'wood' | 'stone' | null;
export type CropState = 'none' | 'growing' | 'mature';
export type Phase = 'dawn' | 'day' | 'dusk' | 'night';

export interface Tile {
  x: number;
  y: number;
  terrain: Terrain;
  resource_type: ResourceType;
  resource_amount: number;
  crop_state: CropState;
  crop_growth_ticks: number;
  crop_colony_id: number | null;
}

export interface WorldSnapshot {
  width: number;
  height: number;
  tiles: Tile[][];
}

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
}

export interface Colony {
  id: number;
  name: string;
  color: string;      // '#rrggbb'
  camp_x: number;
  camp_y: number;
  food_stock: number;
  growing_count: number;
}

export interface SimulationSummary {
  tick: number;
  seed: number | null;
  width: number;
  height: number;
  agent_count: number;
  alive_count: number;
  running: boolean;
  speed: number;
  day: number;
  phase: Phase;
}

export interface WorldStateResponse {
  sim: SimulationSummary;
  world: WorldSnapshot;
  agents: Agent[];
  colonies: Colony[];
  events: EventRow[];
}

export interface SimControlUpdate {
  running?: boolean;
  speed?: number;
}

export interface EventRow {
  tick: number;
  agent_id: number | null;
  type: string;
  description: string | null;
  data: unknown;
}
```

- [ ] **Step 3: Verify typecheck**

```bash
cd /mnt/c/Users/mauro/Dev/Tunnels_Demo/frontend && npx tsc --noEmit
```

Expected: consumers using `sim.day/phase` etc. will flag as errors — that's fine until the components are written.  Existing code should still compile; missing fields on Tile/Agent in mock fixtures will surface.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/types.ts
git commit -m "feat(frontend): extend API types with Colony, Phase, crop fields"
```

---

### Task 24: ClockWidget component

**Files:**
- Create: `frontend/src/components/ClockWidget.tsx`
- Modify: `frontend/src/styles.css` (ClockWidget styles)

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/ClockWidget.test.tsx
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { ClockWidget } from './ClockWidget';

describe('ClockWidget', () => {
  it('renders day and phase', () => {
    render(<ClockWidget day={3} phase="dusk" tick={78} />);
    expect(screen.getByText(/Day 3/)).toBeInTheDocument();
    expect(screen.getByText(/Dusk/i)).toBeInTheDocument();
  });

  it('shows phase progress', () => {
    // tick 78 → 78 % 30 = 18 of 30
    render(<ClockWidget day={3} phase="dusk" tick={78} />);
    expect(screen.getByText('18/30')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run — fails (component missing)**

```bash
cd frontend && npm test -- ClockWidget
```

- [ ] **Step 3: Implement**

```tsx
// frontend/src/components/ClockWidget.tsx
import type { Phase } from '../api/types';

const PHASE_GLYPH: Record<Phase, string> = {
  dawn: '🌅',
  day: '☀️',
  dusk: '🌆',
  night: '🌙',
};

const TICKS_PER_PHASE = 30;

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
```

Add to `frontend/src/styles.css`:

```css
.clock-widget {
  position: absolute;
  top: 12px;
  right: 12px;
  z-index: 10;
  background: rgba(20, 22, 36, 0.8);
  color: #e8ecf2;
  font-family: ui-monospace, SFMono-Regular, monospace;
  padding: 8px 14px;
  border-radius: 6px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  pointer-events: none;
}
.clock-widget__main { display: flex; gap: 8px; align-items: center; font-size: 14px; }
.clock-widget__sep { opacity: 0.4; }
.clock-widget__bar { margin-top: 4px; font-size: 11px; display: flex; gap: 8px; }
.clock-widget__bar-fill { letter-spacing: 1px; }
.clock-widget__bar-count { opacity: 0.7; }
```

- [ ] **Step 4: Verify**

```bash
cd frontend && npm test -- ClockWidget
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ClockWidget.tsx frontend/src/components/ClockWidget.test.tsx frontend/src/styles.css
git commit -m "feat(frontend): ClockWidget showing day/phase/progress"
```

---

### Task 25: Phase tint overlay

**Files:**
- Modify: `frontend/src/styles.css` (phase tint classes)
- Modify: `frontend/src/App.tsx` (add overlay div)

- [ ] **Step 1: Add styles**

Append to `frontend/src/styles.css`:

```css
.phase-tint {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 5;
  transition: background-color 1s ease;
  mix-blend-mode: multiply;
}
.phase-tint[data-phase="dawn"]  { background-color: rgba(255, 165,  80, 0.15); }
.phase-tint[data-phase="day"]   { background-color: rgba(  0,   0,   0, 0.00); }
.phase-tint[data-phase="dusk"]  { background-color: rgba(150,  80, 180, 0.20); }
.phase-tint[data-phase="night"] { background-color: rgba( 20,  30,  80, 0.45); }
```

- [ ] **Step 2: Wire in App.tsx**

In the `<section className="observe">` block, add a phase-tint div over the canvas and ClockWidget at top of main:

```tsx
import { ClockWidget } from './components/ClockWidget';

// Inside return, after the existing hud <header>, before <section className="observe">:
{sim.data && (
  <ClockWidget
    day={sim.data.day}
    phase={sim.data.phase}
    tick={sim.data.tick}
  />
)}

// Inside <section className="observe"><div className="observe__frame">, alongside <WorldCanvas/>:
{sim.data && (
  <div className="phase-tint" data-phase={sim.data.phase} />
)}
```

- [ ] **Step 3: Verify typecheck + smoke**

```bash
cd frontend && npx tsc --noEmit && npm test
```

Expected: no new type errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/styles.css frontend/src/App.tsx
git commit -m "feat(frontend): phase tint overlay + ClockWidget wired in App"
```

---

### Task 26: ColonyPanel HUD

**Files:**
- Create: `frontend/src/components/ColonyPanel.tsx`
- Modify: `frontend/src/styles.css`, `frontend/src/App.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/ColonyPanel.test.tsx
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { ColonyPanel } from './ColonyPanel';

const COLONIES = [
  { id: 1, name: 'Red',   color: '#e74c3c', camp_x: 3,  camp_y: 3,  food_stock: 18, growing_count: 2 },
  { id: 2, name: 'Blue',  color: '#3498db', camp_x: 16, camp_y: 3,  food_stock: 9,  growing_count: 1 },
];

describe('ColonyPanel', () => {
  it('renders one row per colony', () => {
    render(<ColonyPanel colonies={COLONIES} />);
    expect(screen.getByText('Red')).toBeInTheDocument();
    expect(screen.getByText('Blue')).toBeInTheDocument();
  });

  it('shows food_stock and growing_count', () => {
    render(<ColonyPanel colonies={COLONIES} />);
    expect(screen.getByText(/food 18/)).toBeInTheDocument();
    expect(screen.getByText(/fields 2/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run — fails**

```bash
cd frontend && npm test -- ColonyPanel
```

- [ ] **Step 3: Implement**

```tsx
// frontend/src/components/ColonyPanel.tsx
import type { Colony } from '../api/types';

export function ColonyPanel({ colonies }: { colonies: Colony[] }) {
  if (colonies.length === 0) return null;
  return (
    <section className="panel colony-panel">
      <div className="panel__head">
        <span className="panel__dot" />
        <h2 className="panel__title">Colonies</h2>
      </div>
      {colonies.map((c) => (
        <div key={c.id} className="colony-row">
          <span
            className="colony-row__swatch"
            style={{ backgroundColor: c.color }}
            aria-hidden
          />
          <span className="colony-row__name">{c.name}</span>
          <span className="colony-row__stat">food {c.food_stock}</span>
          <span className="colony-row__stat">fields {c.growing_count}</span>
        </div>
      ))}
    </section>
  );
}
```

Append to `frontend/src/styles.css`:

```css
.colony-row {
  display: flex; align-items: center; gap: 10px;
  padding: 4px 2px;
  font-family: ui-monospace, monospace; font-size: 12px;
}
.colony-row__swatch {
  width: 10px; height: 10px; border-radius: 50%;
  border: 1px solid rgba(0,0,0,0.25);
}
.colony-row__name { font-weight: 600; min-width: 54px; }
.colony-row__stat { opacity: 0.78; }
```

Wire in `App.tsx` (next to the other panels in the aside):

```tsx
import { ColonyPanel } from './components/ColonyPanel';

// in aside, after WorldStats panel:
{sim.data && (
  <ColonyPanel colonies={(sim.data as any).colonies ?? []} />
)}
```

**Note**: `sim.data` from `useSimulation()` currently returns `SimulationSummary` (per `/simulation` endpoint) which does NOT include `colonies`. You'll need to source colonies from the `useWorldState` query instead, or add a new hook. Easiest: add a `useColonies` hook that reads from `/world/state`, or extend the ColonyPanel to take colonies from a parent that knows both.

Actually, the simplest pattern matching existing code: add a `useWorldState` hook in `queries.ts` if not present, and have `App` pass `colonies` from it. Inspect `frontend/src/api/queries.ts` — if `/world/state` is already polled there, reuse it. If not, add a small hook:

```typescript
// in queries.ts
import type { WorldStateResponse } from './types';

export function useWorldState() {
  return useQuery<WorldStateResponse>({
    queryKey: ['world-state'],
    queryFn: async () => apiGet<WorldStateResponse>('/world/state'),
    refetchInterval: 500,
  });
}
```

Then App reads `const ws = useWorldState(); const colonies = ws.data?.colonies ?? [];`.

- [ ] **Step 4: Verify**

```bash
cd frontend && npm test -- ColonyPanel && npx tsc --noEmit
```

Expected: 2 pass; typecheck clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ColonyPanel.tsx frontend/src/components/ColonyPanel.test.tsx frontend/src/styles.css frontend/src/App.tsx frontend/src/api/queries.ts
git commit -m "feat(frontend): ColonyPanel HUD — food_stock + growing_count per colony"
```

---

### Task 27: Renderer gains agent tint + camp + crop overlay

**Files:**
- Modify: `frontend/src/render/Renderer.ts` (FrameSnapshot adds colonies)
- Modify: `frontend/src/render/Canvas2DRenderer.ts` (rendering additions)

- [ ] **Step 1: Extend FrameSnapshot**

In `frontend/src/render/Renderer.ts`, add `colonies: Colony[]` to the `FrameSnapshot` interface.

- [ ] **Step 2: Canvas renderer additions**

In `backend/src/render/Canvas2DRenderer.ts`, inside `drawFrame`:

After the terrain pass, before the agent pass:

```typescript
// Camp markers — colored squares at each colony's camp tile.
for (const colony of snap.colonies) {
  const px = colony.camp_x * tilePx;
  const py = colony.camp_y * tilePx;
  ctx.fillStyle = colony.color;
  ctx.globalAlpha = 0.9;
  ctx.fillRect(px + 2, py + 2, tilePx - 4, tilePx - 4);
  ctx.globalAlpha = 1.0;
  ctx.strokeStyle = 'rgba(0,0,0,0.6)';
  ctx.lineWidth = Math.max(1, tilePx * 0.06);
  ctx.strokeRect(px + 2, py + 2, tilePx - 4, tilePx - 4);
}

// Crop overlay — binary sprout/mature dot per tile.
for (let y = 0; y < height; y++) {
  const row = tiles[y];
  if (!row) continue;
  for (let x = 0; x < width; x++) {
    const t = row[x];
    if (!t || t.crop_state === 'none') continue;
    const cx = x * tilePx + tilePx / 2;
    const cy = y * tilePx + tilePx / 2;
    const r = Math.max(2, tilePx * 0.22);
    ctx.fillStyle = t.crop_state === 'mature' ? '#f1c40f' : '#5cbd4a';
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = 'rgba(0,0,0,0.55)';
    ctx.lineWidth = Math.max(1, tilePx * 0.06);
    ctx.stroke();
  }
}
```

Build a color-lookup for agent tint:

```typescript
const colonyColorById = new Map<number, string>();
for (const c of snap.colonies) colonyColorById.set(c.id, c.color);
```

In the agent pass, after the procedural body (non-sprite path), overlay a colored ring or replace `healthColour` with a colony-tinted variant:

```typescript
const colonyColor = a.colony_id != null ? colonyColorById.get(a.colony_id) : undefined;

// Color-tinted outline ring above the pawn silhouette
if (colonyColor) {
  ctx.strokeStyle = colonyColor;
  ctx.lineWidth = Math.max(1.5, tilePx * 0.12);
  ctx.beginPath();
  ctx.arc(cx, cy - r * 0.4, r * 0.55, 0, Math.PI * 2);
  ctx.stroke();
}
```

(Keeps the sprite body intact — a colored halo above its head reads as "this agent belongs to Red colony" without rewriting the sprite pipeline.)

- [ ] **Step 3: Update FrameSnapshot wiring (WorldCanvas → renderer)**

Wherever the snapshot is built (likely `WorldCanvas.tsx`), include `colonies` from world state:

```tsx
const worldState = useWorldState();
const snap: FrameSnapshot = {
  width, height, tiles,
  agents: worldState.data?.agents ?? [],
  colonies: worldState.data?.colonies ?? [],
  // ... existing fields
};
```

- [ ] **Step 4: Verify typecheck + smoke**

```bash
cd frontend && npx tsc --noEmit && npm test
```

Expected: passes.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/render/Renderer.ts frontend/src/render/Canvas2DRenderer.ts frontend/src/components/WorldCanvas.tsx
git commit -m "feat(frontend): render camp squares, crop overlays, colony-tinted agent halo"
```

---

# Phase 5 — Integration + calibration

### Task 28: Plant→grow→harvest round-trip integration test

**Files:**
- Create: `backend/tests/integration/__init__.py` (if missing)
- Create: `backend/tests/integration/test_cultivation_arc.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/integration/test_cultivation_arc.py
from app import db, models
from app.services import simulation_service
from app.engine import config, cycle


def test_plant_grow_harvest_lineage(db_session):
    """Force a full plant → grow → harvest arc with one controlled agent.

    Guards:
      * planted event coord matches crop_matured coord
      * harvested event at same coord, crediting the harvesting colony
      * colony.food_stock jumps by HARVEST_YIELD on that harvest
    """
    simulation_service.create_simulation(
        width=20, height=20, seed=1,
        colonies=4, agents_per_colony=3,
    )
    sim = simulation_service.get_current_simulation()
    # Pick one agent, move to a known empty tile, and seed its state.
    agent = sim.agents[0]
    colony = sim.colonies[agent.colony_id]
    # Find an empty grass tile nearby.
    target = None
    for row in sim.world.tiles:
        for t in row:
            if t.terrain == 'grass' and t.resource_amount == 0 and t.crop_state == 'none':
                target = t
                break
        if target: break
    assert target is not None

    agent.x, agent.y = target.x, target.y
    agent.hunger = 80.0
    sim.current_tick = 30  # start of day

    # Step once — should plant.
    events = simulation_service.step_simulation(ticks=1)
    planted = [e for e in events if e['type'] == 'planted']
    assert len(planted) >= 1
    plant_tx, plant_ty = planted[0]['data']['tile_x'], planted[0]['data']['tile_y']

    # Advance through the rest of day 1's day-phase, full day 2, and into day 3.
    # CROP_MATURE_TICKS = 60 day-phase ticks = 2 in-game days of day phase.
    # Walk forward enough ticks to guarantee maturation.
    # Keep agent on its tile so it's the eventual harvester.
    stock_before = db.session.query(models.Colony).filter_by(id=colony.id).one().food_stock
    agent.hunger = 80.0
    matured_event = None
    for _ in range(300):
        agent.x, agent.y = plant_tx, plant_ty
        # Also reset hunger so decide_action never diverts to forage/socialise
        # from this fixed tile.
        agent.hunger = 80.0
        agent.social = 80.0
        agent.energy = 80.0
        evs = simulation_service.step_simulation(ticks=1)
        for e in evs:
            if e['type'] == 'crop_matured' and e['data']['tile_x'] == plant_tx and e['data']['tile_y'] == plant_ty:
                matured_event = e
                break
        if matured_event: break
    assert matured_event is not None, 'crop never matured'

    # Next day-phase tick with agent on the mature tile → harvest.
    harvested_event = None
    for _ in range(60):
        agent.x, agent.y = plant_tx, plant_ty
        agent.hunger = 80.0
        evs = simulation_service.step_simulation(ticks=1)
        for e in evs:
            if e['type'] == 'harvested' and e['data']['tile_x'] == plant_tx:
                harvested_event = e
                break
        if harvested_event: break
    assert harvested_event is not None, 'agent never harvested the mature tile'
    assert harvested_event['data']['colony_id'] == colony.id
    assert harvested_event['data']['yield_amount'] == config.HARVEST_YIELD

    c_row = db.session.query(models.Colony).filter_by(id=colony.id).one()
    assert c_row.food_stock >= stock_before + config.HARVEST_YIELD \
        or c_row.food_stock == stock_before + config.HARVEST_YIELD - config.EAT_COST * 1, \
        f'food_stock={c_row.food_stock} did not reflect harvest delta'
```

- [ ] **Step 2: Run to verify passes (this is the big gate)**

```bash
docker compose run --rm flask pytest tests/integration/test_cultivation_arc.py -v
```

Expected: 1 passed. If it fails, inspect whether the agent was diverted mid-loop — common cause is missing hunger/social reset inside the loop.

- [ ] **Step 3: Commit**

```bash
mkdir -p backend/tests/integration
touch backend/tests/integration/__init__.py
git add backend/tests/integration/__init__.py backend/tests/integration/test_cultivation_arc.py
git commit -m "test(integration): plant→grow→harvest full lineage round-trip"
```

---

### Task 29: Multi-colony 300-tick arc test

**Files:**
- Modify: `backend/tests/integration/test_cultivation_arc.py`

- [ ] **Step 1: Add test**

Append:

```python
def test_300_tick_arc_has_multi_colony_harvest(db_session):
    """Unforced 300-tick run: at least 2 colonies should harvest at least
    one crop each, with `crop_matured` lineage back to a `planted` event.
    If fewer than 2 colonies participate, balance needs retuning.
    """
    simulation_service.create_simulation(
        width=20, height=20, seed=42,
        colonies=4, agents_per_colony=3,
    )
    all_events = simulation_service.step_simulation(ticks=300)

    planted_by_coord = {
        (e['data']['tile_x'], e['data']['tile_y']): e['data']['colony_id']
        for e in all_events if e['type'] == 'planted'
    }
    matured_coords = {
        (e['data']['tile_x'], e['data']['tile_y'])
        for e in all_events if e['type'] == 'crop_matured'
    }
    # Every matured coord must trace back to a prior planted event
    # (same simulation, so lineage is guaranteed if the engine is honest).
    for coord in matured_coords:
        assert coord in planted_by_coord, f'matured without planted: {coord}'

    harvesting_colonies = {
        e['data']['colony_id']
        for e in all_events if e['type'] == 'harvested'
    }
    assert len(harvesting_colonies) >= 2, \
        f'only {len(harvesting_colonies)} colonies harvested; balance likely off'
```

- [ ] **Step 2: Run to verify (may need rebalance)**

```bash
docker compose run --rm flask pytest tests/integration/test_cultivation_arc.py::test_300_tick_arc_has_multi_colony_harvest -v
```

If it fails because 0 or 1 colonies harvested: this is the calibration signal. Tweak `config.INITIAL_FOOD_STOCK`, `config.WILD_RESOURCE_MAX`, or `config.HARVEST_YIELD` in small steps and re-run. Log the final values in the STUDY_NOTES entry for this milestone.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/integration/test_cultivation_arc.py
git commit -m "test(integration): 300-tick multi-colony harvest arc"
```

---

### Task 30: Full suite + frontend + manual demo run

**Files:** none (verification only)

- [ ] **Step 1: Full backend suite**

```bash
docker compose run --rm flask pytest -q
```

Expected: all green.

- [ ] **Step 2: Frontend tests + typecheck**

```bash
cd frontend && npx tsc --noEmit && npm test
```

- [ ] **Step 3: Clean-slate manual run**

```bash
docker compose down -v
docker compose up -d
docker compose run --rm flask flask db upgrade
curl -X PUT http://localhost/api/v1/simulation \
  -H 'content-type: application/json' \
  -d '{"width":20,"height":20,"seed":42,"colonies":4,"agents_per_colony":3}'
curl -X PATCH http://localhost/api/v1/simulation/control \
  -H 'content-type: application/json' -d '{"running":true,"speed":1}'
```

Open http://localhost in browser. Observe:
- [ ] Clock widget counts up dawn → day → dusk → night
- [ ] Phase tint shifts (orange → clear → purple → navy)
- [ ] 4 camp squares visible in 4 distinct colors at 4 corners
- [ ] Agents appear with colored halo matching camp color
- [ ] After ~300 ticks (~2.5 min), at least one crop (green dot) visible
- [ ] After ~400-500 ticks, at least one mature crop (yellow dot) and a harvest event in the log
- [ ] Colony food_stock diverge across colonies

- [ ] **Step 4: Commit final state**

```bash
git add STUDY_NOTES.md    # if updated with §10.x day/night + cultivation entry
git commit -m "docs: STUDY_NOTES §10 day/night cycle + multi-colony cultivation"
```

(If STUDY_NOTES wasn't touched, skip this step.)

---

## Post-Implementation Checklist

- [ ] All 30 tasks committed in order
- [ ] Backend suite green (89 prior tests + ~20 new = ~110 passing)
- [ ] Frontend typecheck + tests green
- [ ] Clean-slate migration test passed
- [ ] Manual 5-day demo run observed: ≥2 colonies alive at day 5, crop lineage visible
- [ ] ClockWidget + phase tint + camp squares + colored agents all visible
- [ ] Spec referenced in commits for traceability
