# Tunnels — Foundation (Sub-project A) Implementation Plan

**Baseline:** After pre-flight shipped `c45548c`, the green baseline is 215 backend + 37 frontend. Task N Step 6 counts are absolute, not deltas from the plan's original 213.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the vertical Foundation slice for the Tunnels dynastic-civ MVP: scaffolding (new models, `/api/v1/game/*` Flask blueprint, React Router, Zustand), new-game bootstrap with a 5-member starter council, recruitment scene that fills an empty council slot, event-attribution + quarterly digest at week 4. Existing colony sim + its 213 backend tests + 37 frontend tests remain green throughout.

**Architecture:** Pure-engine modules (`engine/world_state.py`, `engine/event_bus.py`, `engine/new_game.py`, `engine/alert_attribution.py`, `engine/council_digest.py`, `engine/tactical/scene_system.py`, `engine/tactical/recruit_scene.py`) keep zero Flask/DB imports. A new `services/game_service.py` adapts engine output to new SQLAlchemy models (`NPC`, `Relationship`, `EventLog`, `Policy`, `SaveMeta`). A new Flask blueprint at `/api/v1/game/*` sits alongside the existing `/api/v1/world/*` blueprint; the world blueprint's response shape is **not** touched. The frontend migrates single-view `App.tsx` into `react-router-dom` routes (`/` tactical default, `/court`, `/council`); a Zustand store holds game state hydrated from `GET /api/v1/game/state` via a new React Query hook.

**Tech Stack:** Python 3.12, Flask 3, Flask-SQLAlchemy 3.x, Alembic (Flask-Migrate), PostgreSQL 18, React 18 + TypeScript, Zustand 5 (already installed at `^5.0.1` — pre-flight verified `create` API compatible with plan's original 4.x assumptions), React Router 6, React Query v5, Vite, Vitest, pytest.

**Spec:** `docs/superpowers/specs/2026-04-17-tunnels-vision-design.md` (committed at 831cdf6)

---

## File Structure

**Backend — engine (pure Python, no Flask/DB):**
- `backend/app/engine/world_state.py` — CREATE: `GameState` dataclass (tick, year, active_layer, alignment_axes dict, npc_registry dict, policies list)
- `backend/app/engine/event_bus.py` — CREATE: `Event` dataclass, `EventBus` with priority tiers P0-P3, `drain(tier_order=…)`
- `backend/app/engine/new_game.py` — CREATE: `new_game(seed)` → `(GameState, events)` with 5 starter councilors
- `backend/app/engine/alert_attribution.py` — CREATE: `attribute(event, state)` adding `source_councilor_id` / `source_policy_id`
- `backend/app/engine/council_digest.py` — CREATE: `build_digest(events, state)` → list of attributed lines
- `backend/app/engine/advance.py` — CREATE: `advance_weeks(state, n, bus)` tick loop for strategic layer only (no tactical)
- `backend/app/engine/tactical/__init__.py` — CREATE
- `backend/app/engine/tactical/scene_system.py` — CREATE: `Scene`, `SceneBeat`, `advance(scene, choice_id)` → next beat or commit, `commit(scene, state)` → events
- `backend/app/engine/tactical/recruit_scene.py` — CREATE: `make_recruit_scene(candidate_id, target_slot, state)` → `Scene`

**Backend — ORM (one file per model):**
- `backend/app/models/npc.py` — CREATE: `NPC` model (tier, name, stats_json, memory_json, status)
- `backend/app/models/relationship.py` — CREATE: `Relationship` model (npc_a_id, npc_b_id, type, strength)
- `backend/app/models/event_log.py` — CREATE: `EventLog` model (tick, tier, source_id, source_type, payload_json)
- `backend/app/models/policy.py` — CREATE: `Policy` model (name, effects_json, active_until_tick)
- `backend/app/models/save_meta.py` — CREATE: `SaveMeta` model (schema_version, playtime, gen_number, seed)
- `backend/app/models/game_state_row.py` — CREATE: `GameStateRow` singleton model (id=1; tick, year, active_layer, alignment_axes_json)
- `backend/app/models/__init__.py` — MODIFY: import new models

**Backend — migration:**
- `backend/migrations/versions/f7e8d9a0b1c2_game_foundation.py` — CREATE

**Backend — services:**
- `backend/app/services/game_mappers.py` — CREATE: `npc_to_row`, `row_to_npc`, `update_npc_row`; mirrors for `EventLog`, `Policy`, `GameStateRow`
- `backend/app/services/game_service.py` — CREATE: `get_state()`, `new_game(seed)`, `advance_weeks(n)`, `recruit_open_slot(slot_specialty)` (starts scene), `advance_scene(choice_id)`, `commit_scene()`

**Backend — routes:**
- `backend/app/routes/game.py` — CREATE: blueprint with:
  - `GET /game/state`
  - `POST /game/new`
  - `POST /game/advance`
  - `POST /game/recruit`
  - `POST /game/scene/advance`
  - `POST /game/scene/commit`
- `backend/app/app.py` — MODIFY: register new blueprint at `/api/v1`

**Backend — tests:**
- `backend/tests/engine/test_event_bus.py` — CREATE
- `backend/tests/engine/test_new_game.py` — CREATE
- `backend/tests/engine/test_alert_attribution.py` — CREATE
- `backend/tests/engine/test_council_digest.py` — CREATE
- `backend/tests/engine/test_advance.py` — CREATE
- `backend/tests/engine/test_scene_system.py` — CREATE
- `backend/tests/engine/test_recruit_scene.py` — CREATE
- `backend/tests/services/test_game_service.py` — CREATE
- `backend/tests/routes/test_game_routes.py` — CREATE
- `backend/tests/integration/test_foundation_arc.py` — CREATE

**Frontend:**
- `frontend/package.json` — MODIFY: add `react-router-dom@6` (zustand already at `^5.0.1`)
- `frontend/src/api/types.ts` — MODIFY: add `GameStateResponse`, `Councilor`, `SceneState`, `DigestLine`
- `frontend/src/api/gameQueries.ts` — CREATE: React Query hooks for `/api/v1/game/*`
- `frontend/src/store/gameStore.ts` — CREATE: Zustand store (game state slice + scene slice)
- `frontend/src/components/CouncilorCard.tsx` — CREATE
- `frontend/src/components/DigestModal.tsx` — CREATE
- `frontend/src/views/TacticalView.tsx` — CREATE: thin wrapper around existing `WorldCanvas`
- `frontend/src/views/CourtView.tsx` — CREATE: hub with tick + year + digest trigger
- `frontend/src/views/CouncilView.tsx` — CREATE: councilor grid + recruit buttons
- `frontend/src/views/RecruitSceneView.tsx` — CREATE
- `frontend/src/App.tsx` — MODIFY: `<BrowserRouter>` with routes
- `frontend/src/styles.css` — MODIFY: `.councilor-card`, `.digest-modal`, `.scene-view` rules

**Frontend — tests:**
- `frontend/src/store/gameStore.test.ts` — CREATE
- `frontend/src/components/CouncilorCard.test.tsx` — CREATE
- `frontend/src/views/CouncilView.test.tsx` — CREATE
- `frontend/src/views/RecruitSceneView.test.tsx` — CREATE
- `frontend/src/App.test.tsx` — MODIFY: update router assertions

**Infra:**
- `nginx/nginx.conf` — MODIFY: add `location = /api/v1/game/state` cache block (1s TTL, same pattern as world/state)

---

## Test Commands

Backend (inside `flask` container, source mounted at `/app`):
```bash
docker compose run --rm flask pytest <path>              # single file/test
docker compose run --rm flask pytest -q                  # whole suite (expect ≥213 passing + new)
docker compose run --rm flask flask db upgrade           # apply migrations
```

Frontend (from `frontend/`):
```bash
npx tsc --noEmit                                         # typecheck
npm test                                                 # vitest (expect ≥37 passing + new)
```

Full-stack manual check:
```bash
docker compose up -d                                     # bring everything up
curl -s http://localhost/api/v1/game/state | jq .        # should 204 No Content with no game
```

---

## Invariants (enforce on every task)

- **Schema ↔ mapper same-commit rule.** Whenever a model column is added, removed, or renamed — including any future `events.actor_id` / `events.target_id` attribution fields, or new `EventLog` / `NPC` / `Policy` columns — update `backend/app/services/mappers.py` (and `backend/app/services/game_mappers.py` once created) in the **same commit** as the migration. `rows_to_world` hard-fails on schema drift; a half-landed schema change breaks rehydration silently between commits.
- **Engine purity.** No Flask / SQLAlchemy imports in `backend/app/engine/**`. Services adapt.
- **Paired-kwargs invariant.** Event construction uses explicit `actor_id=` / `target_id=` / `source_id=` kwargs — never positional — so reviewer + tests can spot a swap.

---

## Phase A — Scaffolding (vertical slice: `GET /api/v1/game/state` returns data end-to-end)

### Task 1: Create new SQLAlchemy models

**Files:**
- Create: `backend/app/models/game_state_row.py`
- Create: `backend/app/models/npc.py`
- Create: `backend/app/models/relationship.py`
- Create: `backend/app/models/event_log.py`
- Create: `backend/app/models/policy.py`
- Create: `backend/app/models/save_meta.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/models/test_game_models.py`:
```python
from app import db
from app.models.game_state_row import GameStateRow
from app.models.npc import NPC
from app.models.event_log import EventLog

def test_game_state_row_singleton(client):
    row = GameStateRow(id=1, tick=0, year=0, active_layer='court',
                       alignment_axes_json={'dictator_benefactor': 0})
    db.session.add(row)
    db.session.commit()
    got = db.session.get(GameStateRow, 1)
    assert got.active_layer == 'court'

def test_npc_roundtrip(client):
    n = NPC(tier=1, name='Aldric', stats_json={'competence': 3, 'loyalty': 4},
            memory_json=[], status='alive')
    db.session.add(n); db.session.commit()
    got = NPC.query.filter_by(name='Aldric').first()
    assert got.stats_json['competence'] == 3

def test_event_log_append_only(client):
    e = EventLog(tick=1, tier='P2', source_id=1, source_type='councilor',
                 payload_json={'kind': 'drama', 'text': 'Steward grumbled'})
    db.session.add(e); db.session.commit()
    assert EventLog.query.count() == 1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose run --rm flask pytest tests/models/test_game_models.py -v
```
Expected: FAIL with `ImportError: cannot import name 'GameStateRow' from 'app.models.game_state_row'`

- [ ] **Step 3: Implement models**

`backend/app/models/game_state_row.py`:
```python
from sqlalchemy.dialects.postgresql import JSONB
from app import db

class GameStateRow(db.Model):
    __tablename__ = 'game_state'
    id = db.Column(db.Integer, primary_key=True)  # enforced singleton via CHECK
    tick = db.Column(db.Integer, nullable=False, default=0)
    year = db.Column(db.Integer, nullable=False, default=0)
    active_layer = db.Column(db.String(16), nullable=False, default='life_sim')
    alignment_axes_json = db.Column(JSONB, nullable=False, default=dict)
    __table_args__ = (
        db.CheckConstraint('id = 1', name='game_state_singleton'),
    )
```

`backend/app/models/npc.py`:
```python
from sqlalchemy.dialects.postgresql import JSONB
from app import db

class NPC(db.Model):
    __tablename__ = 'npcs'
    id = db.Column(db.Integer, primary_key=True)
    tier = db.Column(db.SmallInteger, nullable=False)
    name = db.Column(db.String(64), nullable=False)
    stats_json = db.Column(JSONB, nullable=False, default=dict)
    memory_json = db.Column(JSONB, nullable=False, default=list)
    status = db.Column(db.String(16), nullable=False, default='alive')
    __table_args__ = (
        db.Index('idx_npcs_tier_status', 'tier', 'status'),
    )
```

`backend/app/models/relationship.py`:
```python
from app import db

class Relationship(db.Model):
    __tablename__ = 'relationships'
    id = db.Column(db.Integer, primary_key=True)
    npc_a_id = db.Column(db.Integer, db.ForeignKey('npcs.id', ondelete='CASCADE'), nullable=False)
    npc_b_id = db.Column(db.Integer, db.ForeignKey('npcs.id', ondelete='CASCADE'), nullable=False)
    type = db.Column(db.String(16), nullable=False)  # 'spouse', 'rival', 'councilor', ...
    strength = db.Column(db.SmallInteger, nullable=False, default=0)
    __table_args__ = (
        db.Index('idx_rel_a', 'npc_a_id'),
        db.Index('idx_rel_b', 'npc_b_id'),
    )
```

`backend/app/models/event_log.py`:
```python
from sqlalchemy.dialects.postgresql import JSONB
from app import db

class EventLog(db.Model):
    __tablename__ = 'event_log'
    id = db.Column(db.BigInteger, primary_key=True)
    tick = db.Column(db.Integer, nullable=False)
    tier = db.Column(db.String(4), nullable=False)  # P0 / P1 / P2 / P3
    source_id = db.Column(db.Integer, nullable=True)
    source_type = db.Column(db.String(16), nullable=True)  # 'councilor' / 'policy' / 'system'
    payload_json = db.Column(JSONB, nullable=False, default=dict)
    __table_args__ = (
        db.Index('idx_event_log_source', 'source_id', 'source_type'),
        db.Index('idx_event_log_tick_tier', 'tick', 'tier'),
    )
```

`backend/app/models/policy.py`:
```python
from sqlalchemy.dialects.postgresql import JSONB
from app import db

class Policy(db.Model):
    __tablename__ = 'policies'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(32), nullable=False)
    effects_json = db.Column(JSONB, nullable=False, default=dict)
    active_until_tick = db.Column(db.Integer, nullable=True)
```

`backend/app/models/save_meta.py`:
```python
from app import db

class SaveMeta(db.Model):
    __tablename__ = 'save_meta'
    id = db.Column(db.Integer, primary_key=True)
    schema_version = db.Column(db.Integer, nullable=False, default=1)
    playtime_seconds = db.Column(db.Integer, nullable=False, default=0)
    gen_number = db.Column(db.Integer, nullable=False, default=1)
    seed = db.Column(db.BigInteger, nullable=False)
```

`backend/app/models/__init__.py` — append:
```python
from .game_state_row import GameStateRow
from .npc import NPC
from .relationship import Relationship
from .event_log import EventLog
from .policy import Policy
from .save_meta import SaveMeta
```

- [ ] **Step 4: Generate Alembic migration**

```bash
docker compose run --rm flask flask db migrate -m "game foundation: npc + relationship + event_log + policy + save_meta + game_state"
```

Rename the generated file to `backend/migrations/versions/f7e8d9a0b1c2_game_foundation.py`, open it, verify upgrade creates all 6 tables + indexes + singleton constraint. Add this to the `upgrade()` body at the end, below the auto-generated ops:

```python
# Ensure the singleton invariant is enforceable: no row for GameStateRow yet.
# Seed row is inserted by app.services.game_service.new_game(), not by migration.
```

- [ ] **Step 5: Run tests**

```bash
docker compose run --rm flask flask db upgrade
docker compose run --rm flask pytest tests/models/test_game_models.py -v
```
Expected: 7 passing

- [ ] **Step 6: Run full backend suite — must stay green**

```bash
docker compose run --rm flask pytest -q
```
Expected: all prior 215 passing + 7 new = 222 passing

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/ backend/migrations/versions/f7e8d9a0b1c2_game_foundation.py backend/tests/models/test_game_models.py
git commit -m "feat(models): add NPC, Relationship, EventLog, Policy, SaveMeta, GameStateRow"
```

---

### Task 2: Create game mappers

**Files:**
- Create: `backend/app/services/game_mappers.py`
- Test: `backend/tests/services/test_game_mappers.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/services/test_game_mappers.py
from app.services import game_mappers
from app.models.npc import NPC

def test_npc_row_roundtrip():
    engine_npc = {
        'id': 1, 'tier': 1, 'name': 'Aldric',
        'stats': {'competence': 3, 'loyalty': 4, 'ambition': 2, 'specialty': 'steward'},
        'memory': [], 'status': 'alive',
    }
    row = game_mappers.npc_to_row(engine_npc)
    assert isinstance(row, NPC)
    assert row.stats_json['competence'] == 3
    back = game_mappers.row_to_npc(row)
    assert back['name'] == 'Aldric'
    assert back['stats']['specialty'] == 'steward'
```

- [ ] **Step 2: Run test — expect ImportError**

```bash
docker compose run --rm flask pytest backend/tests/services/test_game_mappers.py -v
```

- [ ] **Step 3: Implement mappers**

`backend/app/services/game_mappers.py`:
```python
"""Row↔engine-dict conversions for game foundation models.

Keep these pure (no db.session access) — service layer owns commits.
"""
from app.models.npc import NPC
from app.models.event_log import EventLog
from app.models.policy import Policy
from app.models.game_state_row import GameStateRow


def npc_to_row(npc: dict) -> NPC:
    return NPC(
        id=npc.get('id'),
        tier=npc['tier'],
        name=npc['name'],
        stats_json=npc['stats'],
        memory_json=npc.get('memory', []),
        status=npc.get('status', 'alive'),
    )


def row_to_npc(row: NPC) -> dict:
    return {
        'id': row.id,
        'tier': row.tier,
        'name': row.name,
        'stats': row.stats_json,
        'memory': row.memory_json,
        'status': row.status,
    }


def update_npc_row(row: NPC, npc: dict) -> None:
    row.stats_json = npc['stats']
    row.memory_json = npc.get('memory', [])
    row.status = npc.get('status', row.status)


def event_to_row(event: dict) -> EventLog:
    return EventLog(
        tick=event['tick'],
        tier=event['tier'],
        source_id=event.get('source_id'),
        source_type=event.get('source_type'),
        payload_json=event.get('payload', {}),
    )


def row_to_event(row: EventLog) -> dict:
    return {
        'tick': row.tick,
        'tier': row.tier,
        'source_id': row.source_id,
        'source_type': row.source_type,
        'payload': row.payload_json,
    }


def policy_to_row(policy: dict) -> Policy:
    return Policy(
        id=policy.get('id'),
        name=policy['name'],
        effects_json=policy['effects'],
        active_until_tick=policy.get('active_until_tick'),
    )


def row_to_policy(row: Policy) -> dict:
    return {
        'id': row.id,
        'name': row.name,
        'effects': row.effects_json,
        'active_until_tick': row.active_until_tick,
    }


def state_to_row(state: dict) -> GameStateRow:
    return GameStateRow(
        id=1,
        tick=state['tick'],
        year=state['year'],
        active_layer=state['active_layer'],
        alignment_axes_json=state['alignment_axes'],
    )


def row_to_state(row: GameStateRow) -> dict:
    return {
        'tick': row.tick,
        'year': row.year,
        'active_layer': row.active_layer,
        'alignment_axes': row.alignment_axes_json,
    }


def update_state_row(row: GameStateRow, state: dict) -> None:
    row.tick = state['tick']
    row.year = state['year']
    row.active_layer = state['active_layer']
    row.alignment_axes_json = state['alignment_axes']
```

- [ ] **Step 4: Run tests**

```bash
docker compose run --rm flask pytest backend/tests/services/test_game_mappers.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/game_mappers.py backend/tests/services/test_game_mappers.py
git commit -m "feat(services): add game_mappers (row↔engine-dict)"
```

---

### Task 3: Engine — `world_state.py` (shared canonical state)

**Files:**
- Create: `backend/app/engine/world_state.py`
- Test: `backend/tests/engine/test_world_state.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/engine/test_world_state.py
from app.engine.world_state import GameState, empty_state

def test_empty_state_has_defaults():
    s = empty_state(seed=42)
    assert s.tick == 0
    assert s.year == 0
    assert s.active_layer == 'court'
    assert s.alignment_axes == {'dictator_benefactor': 0}
    assert s.npcs == {}
    assert s.policies == []
    assert s.seed == 42

def test_state_is_mutable():
    s = empty_state(seed=1)
    s.tick = 10
    s.npcs[1] = {'name': 'Aldric', 'tier': 1}
    assert s.tick == 10
    assert s.npcs[1]['name'] == 'Aldric'
```

- [ ] **Step 2: Run it — expect import failure**

```bash
docker compose run --rm flask pytest backend/tests/engine/test_world_state.py -v
```

- [ ] **Step 3: Implement**

`backend/app/engine/world_state.py`:
```python
"""Canonical in-memory game state.

Pure Python — no Flask, no DB. Service layer owns (de)hydration.
"""
from dataclasses import dataclass, field


@dataclass
class GameState:
    seed: int
    tick: int = 0
    year: int = 0
    active_layer: str = 'court'  # 'court' | 'tactical' | 'overworld'
    alignment_axes: dict = field(default_factory=lambda: {'dictator_benefactor': 0})
    # npcs[id] = {tier, name, stats, memory, status, slot?}
    npcs: dict = field(default_factory=dict)
    # policies = [{id, name, effects, active_until_tick}]
    policies: list = field(default_factory=list)


def empty_state(seed: int) -> GameState:
    return GameState(seed=seed)
```

- [ ] **Step 4: Run — expect PASS**

```bash
docker compose run --rm flask pytest backend/tests/engine/test_world_state.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/engine/world_state.py backend/tests/engine/test_world_state.py
git commit -m "feat(engine): add world_state.GameState"
```

---

### Task 4: Engine — `event_bus.py` (priority tiers P0-P3)

**Files:**
- Create: `backend/app/engine/event_bus.py`
- Test: `backend/tests/engine/test_event_bus.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/engine/test_event_bus.py
from app.engine.event_bus import Event, EventBus, TIERS

def test_events_drain_in_priority_order():
    bus = EventBus()
    bus.publish(Event(tier='P3', tick=1, source_id=None, source_type=None, payload={'kind': 'gossip'}))
    bus.publish(Event(tier='P0', tick=1, source_id=None, source_type=None, payload={'kind': 'coup'}))
    bus.publish(Event(tier='P2', tick=1, source_id=None, source_type=None, payload={'kind': 'drama'}))
    drained = bus.drain()
    assert [e.tier for e in drained] == ['P0', 'P2', 'P3']

def test_within_tier_insertion_order():
    bus = EventBus()
    for i in range(3):
        bus.publish(Event(tier='P2', tick=1, source_id=None, source_type=None,
                          payload={'kind': 'drama', 'n': i}))
    drained = bus.drain()
    assert [e.payload['n'] for e in drained] == [0, 1, 2]

def test_tiers_constant_ordering():
    assert TIERS == ('P0', 'P1', 'P2', 'P3')
```

- [ ] **Step 2: Run — expect fail**

```bash
docker compose run --rm flask pytest backend/tests/engine/test_event_bus.py -v
```

- [ ] **Step 3: Implement**

`backend/app/engine/event_bus.py`:
```python
"""Priority-tiered event bus. Transactional per drain.

Tiers (highest priority first):
  P0 existential  — succession crisis, siege, coup (zero in MVP)
  P1 strategic    — war declared, plague, spouse death
  P2 social       — councilor drama, heir milestone, betrayal
  P3 flavor       — gossip, passing traveller, minor trade news
"""
from dataclasses import dataclass, field
from typing import Any

TIERS = ('P0', 'P1', 'P2', 'P3')


@dataclass
class Event:
    tier: str
    tick: int
    source_id: int | None
    source_type: str | None  # 'councilor' | 'policy' | 'system'
    payload: dict[str, Any] = field(default_factory=dict)


class EventBus:
    def __init__(self) -> None:
        self._queue: list[Event] = []

    def publish(self, event: Event) -> None:
        if event.tier not in TIERS:
            raise ValueError(f"invalid tier {event.tier!r}; expected one of {TIERS}")
        self._queue.append(event)

    def drain(self) -> list[Event]:
        # Stable sort: tier first (P0 < P1 < P2 < P3 by index), insertion order within tier.
        order = {t: i for i, t in enumerate(TIERS)}
        drained = sorted(self._queue, key=lambda e: order[e.tier])
        self._queue.clear()
        return drained

    def peek(self) -> list[Event]:
        return list(self._queue)
```

- [ ] **Step 4: Run — PASS**

```bash
docker compose run --rm flask pytest backend/tests/engine/test_event_bus.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/engine/event_bus.py backend/tests/engine/test_event_bus.py
git commit -m "feat(engine): add event_bus with P0-P3 priority tiers"
```

---

### Task 5: Service — `game_service.get_state()` skeleton

**Files:**
- Create: `backend/app/services/game_service.py`
- Test: `backend/tests/services/test_game_service.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/services/test_game_service.py
from app.services import game_service
from app.models.game_state_row import GameStateRow
from app import db

def test_get_state_returns_none_when_no_game(client):
    assert game_service.get_state() is None

def test_get_state_returns_serialized_state_when_row_exists(client):
    row = GameStateRow(id=1, tick=7, year=0, active_layer='court',
                       alignment_axes_json={'dictator_benefactor': 2})
    db.session.add(row); db.session.commit()
    s = game_service.get_state()
    assert s['tick'] == 7
    assert s['alignment_axes']['dictator_benefactor'] == 2
    assert s['npcs'] == []
```

- [ ] **Step 2: Run — fail**

```bash
docker compose run --rm flask pytest backend/tests/services/test_game_service.py -v
```

- [ ] **Step 3: Implement**

`backend/app/services/game_service.py`:
```python
"""Adapter between Flask routes, DB, and the pure-engine game modules.

No global singleton (contrast `simulation_service._current_sim`) — game state
is persisted each request and re-hydrated on read, so horizontal scaling is
not blocked the way the legacy colony sim is.
"""
from app import db
from app.models.game_state_row import GameStateRow
from app.models.npc import NPC
from app.models.policy import Policy
from app.services import game_mappers


def get_state() -> dict | None:
    row = db.session.get(GameStateRow, 1)
    if row is None:
        return None
    state = game_mappers.row_to_state(row)
    state['npcs'] = [game_mappers.row_to_npc(n) for n in NPC.query.order_by(NPC.id).all()]
    state['policies'] = [game_mappers.row_to_policy(p) for p in Policy.query.all()]
    return state
```

- [ ] **Step 4: Run — PASS**

```bash
docker compose run --rm flask pytest backend/tests/services/test_game_service.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/game_service.py backend/tests/services/test_game_service.py
git commit -m "feat(services): add game_service.get_state skeleton"
```

---

### Task 6: Flask blueprint — `GET /api/v1/game/state`

**Files:**
- Create: `backend/app/routes/game.py`
- Modify: `backend/app/app.py` (register blueprint)
- Test: `backend/tests/routes/test_game_routes.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/routes/test_game_routes.py
def test_get_state_returns_204_before_new_game(client):
    resp = client.get('/api/v1/game/state')
    assert resp.status_code == 204  # no content = no game started

def test_world_state_endpoint_still_works(client):
    # Regression guard: /api/v1/world/state must not change shape
    resp = client.get('/api/v1/world/state')
    # (world/state responds 404 or 200 depending on whether a colony sim exists;
    # we only assert it does not 500 from our changes)
    assert resp.status_code != 500
```

- [ ] **Step 2: Run — expect 404 for game route (not registered yet)**

```bash
docker compose run --rm flask pytest backend/tests/routes/test_game_routes.py -v
```

- [ ] **Step 3: Implement blueprint**

`backend/app/routes/game.py`:
```python
"""Flask blueprint for the dynastic-civ game layer.

Sits alongside the existing simulation blueprint. Shape of /api/v1/world/*
must not change — the Foundation slice adds new routes, never modifies old.
"""
from flask import Blueprint, jsonify

from app.services import game_service

bp = Blueprint('game', __name__)


@bp.get('/game/state')
def get_state():
    state = game_service.get_state()
    if state is None:
        return '', 204
    return jsonify(state), 200
```

- [ ] **Step 4: Register blueprint**

Modify `backend/app/app.py` — find where `simulation_bp` is registered and add the game blueprint below it:

```python
# existing:
from app.routes.simulation import bp as simulation_bp
app.register_blueprint(simulation_bp, url_prefix="/api/v1")

# ADD:
from app.routes.game import bp as game_bp
app.register_blueprint(game_bp, url_prefix="/api/v1")
```

- [ ] **Step 5: Run — expect PASS**

```bash
docker compose run --rm flask pytest backend/tests/routes/test_game_routes.py -v
```

- [ ] **Step 6: Full backend suite**

```bash
docker compose run --rm flask pytest -q
```
Expected: all prior + new = stays green

- [ ] **Step 7: Commit**

```bash
git add backend/app/routes/game.py backend/app/app.py backend/tests/routes/test_game_routes.py
git commit -m "feat(routes): add /api/v1/game/state blueprint"
```

---

### Task 7: Frontend — install React Router + Zustand

**Files:**
- Modify: `frontend/package.json`, `frontend/package-lock.json`

- [ ] **Step 1: Install**

```bash
cd frontend && npm install react-router-dom@6   # zustand already installed at ^5.0.1
```

- [ ] **Step 2: Verify types resolve**

```bash
npx tsc --noEmit
```
Expected: no new errors

- [ ] **Step 3: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "chore(deps): add react-router-dom"
```

---

### Task 8: Frontend — Zustand store skeleton + gameQueries hook

**Files:**
- Create: `frontend/src/store/gameStore.ts`
- Create: `frontend/src/api/gameQueries.ts`
- Modify: `frontend/src/api/types.ts`
- Test: `frontend/src/store/gameStore.test.ts`

- [ ] **Step 1: Write the failing store test**

```ts
// frontend/src/store/gameStore.test.ts
import { describe, it, expect, beforeEach } from 'vitest';
import { useGameStore } from './gameStore';

describe('useGameStore', () => {
  beforeEach(() => { useGameStore.setState(useGameStore.getInitialState()); });

  it('starts with null game state', () => {
    expect(useGameStore.getState().game).toBeNull();
  });

  it('setGame replaces state', () => {
    useGameStore.getState().setGame({
      tick: 5, year: 0, active_layer: 'court',
      alignment_axes: { dictator_benefactor: 0 },
      npcs: [], policies: [],
    });
    expect(useGameStore.getState().game?.tick).toBe(5);
  });
});
```

- [ ] **Step 2: Run — expect ImportError**

```bash
cd frontend && npm test -- gameStore
```

- [ ] **Step 3: Extend types.ts**

Append to `frontend/src/api/types.ts`:
```ts
export type CouncilorStats = {
  competence: number;
  loyalty: number;
  ambition: number;
  specialty: 'steward' | 'marshal' | 'spy' | 'chancellor' | 'priest';
};

export type Councilor = {
  id: number;
  tier: number;
  name: string;
  stats: CouncilorStats;
  memory: unknown[];
  status: 'alive' | 'dead' | 'away';
};

export type GameStateResponse = {
  tick: number;
  year: number;
  active_layer: 'court' | 'tactical' | 'overworld';
  alignment_axes: { dictator_benefactor: number };
  npcs: Councilor[];
  policies: { id: number; name: string; effects: Record<string, unknown>; active_until_tick: number | null }[];
};
```

- [ ] **Step 4: Implement store**

`frontend/src/store/gameStore.ts`:
```ts
import { create } from 'zustand';
import type { GameStateResponse } from '../api/types';

type GameStoreState = {
  game: GameStateResponse | null;
  setGame: (g: GameStateResponse | null) => void;
};

export const useGameStore = create<GameStoreState>()((set) => ({
  game: null,
  setGame: (g) => set({ game: g }),
}));
```

- [ ] **Step 5: Implement query hook**

`frontend/src/api/gameQueries.ts`:
```ts
import { useQuery } from '@tanstack/react-query';
import { useEffect } from 'react';
import { apiGet } from './client';
import type { GameStateResponse } from './types';
import { useGameStore } from '../store/gameStore';

const GAME_STATE_KEY = ['gameState'] as const;
const POLL_INTERVAL_MS = 1000;

export function useGameState() {
  const setGame = useGameStore((s) => s.setGame);
  const q = useQuery({
    queryKey: GAME_STATE_KEY,
    queryFn: async (): Promise<GameStateResponse | null> => {
      try {
        return await apiGet<GameStateResponse>('/game/state');
      } catch (err) {
        // 204 → apiGet throws; treat as "no game"
        return null;
      }
    },
    refetchInterval: POLL_INTERVAL_MS,
  });
  useEffect(() => { setGame(q.data ?? null); }, [q.data, setGame]);
  return q;
}
```

- [ ] **Step 6: Run store test**

```bash
cd frontend && npm test -- gameStore
```
Expected: PASS

- [ ] **Step 7: Typecheck**

```bash
cd frontend && npx tsc --noEmit
```
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add frontend/src/store/ frontend/src/api/gameQueries.ts frontend/src/api/types.ts frontend/src/store/gameStore.test.ts
git commit -m "feat(frontend): add gameStore + useGameState hook"
```

---

### Task 9: Frontend — migrate App.tsx to React Router with /court route

**Files:**
- Modify: `frontend/src/App.tsx`
- Create: `frontend/src/views/TacticalView.tsx`
- Create: `frontend/src/views/CourtView.tsx`
- Modify: `frontend/src/App.test.tsx`

- [ ] **Step 1: Extract current App body into TacticalView**

Create `frontend/src/views/TacticalView.tsx` containing the existing `<WorldCanvas />` + HUD JSX currently rendered in App.tsx. Copy, do not reformat. This is a lift, not a refactor.

- [ ] **Step 2: Stub CourtView**

`frontend/src/views/CourtView.tsx`:
```tsx
import { useGameState } from '../api/gameQueries';

export default function CourtView() {
  const { data: game, isLoading } = useGameState();
  if (isLoading) return <p>Loading court…</p>;
  if (!game) return <p>No game in progress. <button disabled>New Game (coming soon)</button></p>;
  return (
    <div className="court-view">
      <h2>Court — Year {game.year}, Week {Math.floor(game.tick / 7)}</h2>
      <p>Councilors: {game.npcs.length}</p>
      <nav>
        <a href="/council">Council</a> · <a href="/">Tactical</a>
      </nav>
    </div>
  );
}
```

- [ ] **Step 3: Rewrite App.tsx to use BrowserRouter**

`frontend/src/App.tsx`:
```tsx
import { BrowserRouter, Routes, Route, Link } from 'react-router-dom';
import TacticalView from './views/TacticalView';
import CourtView from './views/CourtView';

export default function App() {
  return (
    <BrowserRouter>
      <header className="app-nav">
        <Link to="/">Tactical</Link> · <Link to="/court">Court</Link>
      </header>
      <Routes>
        <Route path="/" element={<TacticalView />} />
        <Route path="/court" element={<CourtView />} />
      </Routes>
    </BrowserRouter>
  );
}
```

- [ ] **Step 4: Update App.test.tsx**

Replace any `render(<App/>)` assertions that expected the canvas to be the root element; instead assert the nav link is present:

```tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import App from './App';

describe('App', () => {
  it('renders navigation links', () => {
    render(<App />);
    expect(screen.getByText('Tactical')).toBeInTheDocument();
    expect(screen.getByText('Court')).toBeInTheDocument();
  });
});
```

(If `App.test.tsx` doesn't currently exist, create it. If it does, wrap existing canvas-specific assertions in a describe for TacticalView and port them to `frontend/src/views/TacticalView.test.tsx` unchanged.)

- [ ] **Step 5: Typecheck + test**

```bash
cd frontend && npx tsc --noEmit && npm test
```
Expected: all prior 37 passing + App.test updated. No regressions.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/App.tsx frontend/src/views/ frontend/src/App.test.tsx
git commit -m "feat(frontend): migrate to react-router-dom, add /court placeholder"
```

---

### Task 10: nginx cache block for `/api/v1/game/state`

**Files:**
- Modify: `nginx/nginx.conf`

- [ ] **Step 1: Edit**

Find the existing `location = /api/v1/world/state` block. Below it, add:

```nginx
    location = /api/v1/game/state {
      proxy_pass http://flask:5000;
      proxy_set_header Host $host;

      proxy_cache world_state;  # reuse the same cache zone; keys differ by URI
      proxy_cache_key "$scheme$request_method$host$request_uri";
      proxy_cache_valid 200 1s;
      proxy_cache_valid 204 1s;
      proxy_cache_lock on;
      proxy_cache_lock_timeout 500ms;
      add_header X-Cache-Status $upstream_cache_status;
    }
```

- [ ] **Step 2: Reload nginx + smoke test**

```bash
docker compose up -d nginx
curl -sI http://localhost/api/v1/game/state
# First request: MISS (or 204 with X-Cache-Status)
curl -sI http://localhost/api/v1/game/state
# Second request within 1s: HIT
```

- [ ] **Step 3: Commit**

```bash
git add nginx/nginx.conf
git commit -m "chore(nginx): cache /api/v1/game/state (1s TTL, matches world/state pattern)"
```

**Phase A exit criteria:** `curl http://localhost/api/v1/game/state` returns `204` when no game exists. Frontend `/court` route renders "No game in progress". Full test suites still green (216 backend, 38 frontend).

---

## Phase B — New game + starter council (vertical slice: start game → council visible)

### Task 11: Engine — `new_game.py` with deterministic starter council

**Files:**
- Create: `backend/app/engine/new_game.py`
- Test: `backend/tests/engine/test_new_game.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/engine/test_new_game.py
from app.engine.new_game import new_game, SPECIALTIES, NEW_GAME_COUNCIL_GENEROSITY

def test_new_game_has_5_councilors_one_per_specialty():
    state, events = new_game(seed=42)
    councilors = [n for n in state.npcs.values() if n.get('slot') == 'council']
    assert len(councilors) == 5
    specialties = {n['stats']['specialty'] for n in councilors}
    assert specialties == set(SPECIALTIES)

def test_new_game_is_deterministic():
    s1, _ = new_game(seed=42)
    s2, _ = new_game(seed=42)
    names_1 = [n['name'] for n in s1.npcs.values()]
    names_2 = [n['name'] for n in s2.npcs.values()]
    assert names_1 == names_2

def test_forgiving_first_run_boosts_starter_stats():
    state, _ = new_game(seed=42)
    councilors = [n for n in state.npcs.values() if n.get('slot') == 'council']
    # At least one councilor per specialty has competence >= 3 after generosity=1.2
    by_specialty = {n['stats']['specialty']: n for n in councilors}
    for spec in SPECIALTIES:
        assert by_specialty[spec]['stats']['competence'] >= 3, f"{spec} too weak for MVP first run"

def test_new_game_emits_bootstrap_event():
    state, events = new_game(seed=42)
    tiers = [e.tier for e in events]
    assert 'P2' in tiers  # at least one "council assembled" social event
```

- [ ] **Step 2: Run — fail**

```bash
docker compose run --rm flask pytest backend/tests/engine/test_new_game.py -v
```

- [ ] **Step 3: Implement**

`backend/app/engine/new_game.py`:
```python
"""Starter-world generation.

Forgiving-first-run rule (spec §2 council UX 1c): generosity factor boosts
the starting council's competence by ~20% so that playtest session 1 is not
doomed by RNG. Dev-only constant — no difficulty UI in MVP.
"""
import random
from app.engine.world_state import GameState, empty_state
from app.engine.event_bus import Event

SPECIALTIES = ('steward', 'marshal', 'spy', 'chancellor', 'priest')
NEW_GAME_COUNCIL_GENEROSITY = 1.2

_NAME_POOL = [
    'Aldric', 'Beatrix', 'Corwin', 'Dagna', 'Elric', 'Fiora',
    'Gareth', 'Helva', 'Iven', 'Jorun', 'Kara', 'Lysa',
    'Mael', 'Nyra', 'Orin', 'Perrin', 'Quenna', 'Roric',
    'Selene', 'Torvin', 'Ulric', 'Vesna',
]


def _roll_stats(rng: random.Random, specialty: str, generosity: float) -> dict:
    base_competence = rng.randint(1, 5)
    boosted = min(5, int(round(base_competence * generosity)))
    return {
        'competence': boosted,
        'loyalty': rng.randint(1, 5),
        'ambition': rng.randint(1, 5),
        'specialty': specialty,
    }


def new_game(seed: int) -> tuple[GameState, list[Event]]:
    rng = random.Random(seed)
    state = empty_state(seed=seed)
    events: list[Event] = []

    names = rng.sample(_NAME_POOL, k=len(SPECIALTIES))
    for i, specialty in enumerate(SPECIALTIES):
        npc_id = i + 1
        state.npcs[npc_id] = {
            'id': npc_id,
            'tier': 1,
            'name': names[i],
            'slot': 'council',
            'stats': _roll_stats(rng, specialty, NEW_GAME_COUNCIL_GENEROSITY),
            'memory': [],
            'status': 'alive',
        }
        events.append(Event(
            tier='P2', tick=0, source_id=npc_id, source_type='councilor',
            payload={'kind': 'council_appointed', 'name': names[i], 'specialty': specialty},
        ))

    events.append(Event(
        tier='P2', tick=0, source_id=None, source_type='system',
        payload={'kind': 'council_assembled', 'count': len(SPECIALTIES)},
    ))
    return state, events
```

- [ ] **Step 4: Run — PASS**

```bash
docker compose run --rm flask pytest backend/tests/engine/test_new_game.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/engine/new_game.py backend/tests/engine/test_new_game.py
git commit -m "feat(engine): starter council generation with forgiving first run"
```

---

### Task 12: Service — `game_service.new_game()` + `POST /api/v1/game/new`

**Files:**
- Modify: `backend/app/services/game_service.py`
- Modify: `backend/app/routes/game.py`
- Modify: `backend/tests/services/test_game_service.py`
- Modify: `backend/tests/routes/test_game_routes.py`

- [ ] **Step 1: Write failing service test**

Append to `backend/tests/services/test_game_service.py`:
```python
def test_new_game_persists_starter_council(client):
    state = game_service.new_game(seed=42)
    assert len([n for n in state['npcs'] if n.get('slot') == 'council']) == 5
    # Re-read: ensure it persisted
    loaded = game_service.get_state()
    assert len(loaded['npcs']) == 5

def test_new_game_twice_replaces(client):
    game_service.new_game(seed=1)
    n1 = len(game_service.get_state()['npcs'])
    game_service.new_game(seed=2)
    assert len(game_service.get_state()['npcs']) == n1  # 5
```

- [ ] **Step 2: Write failing route test**

Append to `backend/tests/routes/test_game_routes.py`:
```python
def test_post_new_game_returns_state(client):
    resp = client.post('/api/v1/game/new', json={'seed': 42})
    assert resp.status_code == 201
    body = resp.get_json()
    assert len(body['npcs']) == 5
    assert body['tick'] == 0

def test_post_new_game_requires_seed(client):
    resp = client.post('/api/v1/game/new', json={})
    assert resp.status_code == 400
```

- [ ] **Step 3: Run — fail**

```bash
docker compose run --rm flask pytest backend/tests/services/test_game_service.py backend/tests/routes/test_game_routes.py -v
```

- [ ] **Step 4: Extend service**

Append to `backend/app/services/game_service.py`:
```python
from app.engine import new_game as new_game_engine
from app.models.npc import NPC
from app.models.event_log import EventLog
from app.models.save_meta import SaveMeta


def new_game(seed: int) -> dict:
    """Create a fresh game. Wipes any previous save rows, persists the new state."""
    # Wipe in dependency order (relationships → npcs → event_log → policies → state → save_meta)
    db.session.execute(db.text('TRUNCATE relationships, npcs, event_log, policies, game_state, save_meta RESTART IDENTITY CASCADE'))

    state, events = new_game_engine.new_game(seed=seed)

    db.session.add(game_mappers.state_to_row({
        'tick': state.tick, 'year': state.year,
        'active_layer': state.active_layer,
        'alignment_axes': state.alignment_axes,
    }))
    for npc in state.npcs.values():
        db.session.add(game_mappers.npc_to_row(npc))
    for ev in events:
        db.session.add(game_mappers.event_to_row({
            'tick': ev.tick, 'tier': ev.tier,
            'source_id': ev.source_id, 'source_type': ev.source_type,
            'payload': ev.payload,
        }))
    db.session.add(SaveMeta(seed=seed, gen_number=1))
    db.session.commit()
    return get_state()
```

- [ ] **Step 5: Extend route**

Append to `backend/app/routes/game.py`:
```python
from flask import request


def _require_int(value, field):
    if not isinstance(value, int):
        from werkzeug.exceptions import BadRequest
        raise BadRequest(f"{field!r} must be int")
    return value


@bp.post('/game/new')
def post_new_game():
    body = request.get_json(silent=True) or {}
    if 'seed' not in body:
        return {'error': "'seed' is required"}, 400
    seed = _require_int(body['seed'], 'seed')
    state = game_service.new_game(seed=seed)
    return jsonify(state), 201
```

- [ ] **Step 6: Run — PASS**

```bash
docker compose run --rm flask pytest backend/tests/services/test_game_service.py backend/tests/routes/test_game_routes.py -v
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/game_service.py backend/app/routes/game.py backend/tests/services/test_game_service.py backend/tests/routes/test_game_routes.py
git commit -m "feat(game): POST /api/v1/game/new bootstraps starter council"
```

---

### Task 13: Frontend — CouncilorCard + CouncilView

**Files:**
- Create: `frontend/src/components/CouncilorCard.tsx`
- Create: `frontend/src/views/CouncilView.tsx`
- Test: `frontend/src/components/CouncilorCard.test.tsx`
- Test: `frontend/src/views/CouncilView.test.tsx`
- Modify: `frontend/src/App.tsx` (add /council route)
- Modify: `frontend/src/views/CourtView.tsx` (add "New Game" button)
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: Failing CouncilorCard test**

```tsx
// frontend/src/components/CouncilorCard.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import CouncilorCard from './CouncilorCard';

describe('CouncilorCard', () => {
  it('renders name, specialty, and all four stats', () => {
    render(<CouncilorCard councilor={{
      id: 1, tier: 1, name: 'Aldric', memory: [], status: 'alive',
      stats: { competence: 3, loyalty: 4, ambition: 2, specialty: 'steward' },
    }} />);
    expect(screen.getByText('Aldric')).toBeInTheDocument();
    expect(screen.getByText(/steward/i)).toBeInTheDocument();
    expect(screen.getByLabelText('competence')).toHaveTextContent('3');
    expect(screen.getByLabelText('loyalty')).toHaveTextContent('4');
    expect(screen.getByLabelText('ambition')).toHaveTextContent('2');
  });
});
```

- [ ] **Step 2: Run — fail**

```bash
cd frontend && npm test -- CouncilorCard
```

- [ ] **Step 3: Implement CouncilorCard**

`frontend/src/components/CouncilorCard.tsx`:
```tsx
import type { Councilor } from '../api/types';

export default function CouncilorCard({ councilor }: { councilor: Councilor }) {
  const s = councilor.stats;
  return (
    <article className="councilor-card">
      <header>
        <h3>{councilor.name}</h3>
        <span className="specialty">{s.specialty}</span>
      </header>
      <dl className="stats">
        <div><dt>Competence</dt><dd aria-label="competence">{s.competence}</dd></div>
        <div><dt>Loyalty</dt>   <dd aria-label="loyalty">{s.loyalty}</dd></div>
        <div><dt>Ambition</dt>  <dd aria-label="ambition">{s.ambition}</dd></div>
      </dl>
    </article>
  );
}
```

- [ ] **Step 4: Failing CouncilView test**

```tsx
// frontend/src/views/CouncilView.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import CouncilView from './CouncilView';
import { useGameStore } from '../store/gameStore';

function renderWith(councilors: any[]) {
  useGameStore.setState({
    game: {
      tick: 0, year: 0, active_layer: 'court',
      alignment_axes: { dictator_benefactor: 0 },
      npcs: councilors, policies: [],
    },
    setGame: useGameStore.getState().setGame,
  });
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter><CouncilView /></MemoryRouter>
    </QueryClientProvider>
  );
}

describe('CouncilView', () => {
  it('lists 5 councilor cards when state has 5 NPCs', () => {
    renderWith([1, 2, 3, 4, 5].map((i) => ({
      id: i, tier: 1, name: `NPC${i}`, memory: [], status: 'alive',
      stats: { competence: 3, loyalty: 3, ambition: 3,
               specialty: ['steward','marshal','spy','chancellor','priest'][i-1] as any },
    })));
    expect(screen.getAllByRole('article')).toHaveLength(5);
  });
});
```

- [ ] **Step 5: Implement CouncilView**

`frontend/src/views/CouncilView.tsx`:
```tsx
import { useGameStore } from '../store/gameStore';
import CouncilorCard from '../components/CouncilorCard';
import { Link } from 'react-router-dom';

export default function CouncilView() {
  const game = useGameStore((s) => s.game);
  if (!game) return <p>No game. <Link to="/court">Start one →</Link></p>;
  const council = game.npcs.filter((n) => n.status === 'alive');
  return (
    <section className="council-view">
      <h2>The Council</h2>
      <div className="councilor-grid">
        {council.map((c) => <CouncilorCard key={c.id} councilor={c} />)}
      </div>
      <nav><Link to="/court">← Back to court</Link></nav>
    </section>
  );
}
```

- [ ] **Step 6: Update CourtView with New Game button**

Replace `CourtView.tsx` body's placeholder section:
```tsx
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiPost } from '../api/client';
import { Link } from 'react-router-dom';
import { useGameState } from '../api/gameQueries';

export default function CourtView() {
  const { data: game, isLoading } = useGameState();
  const qc = useQueryClient();
  const newGame = useMutation({
    mutationFn: () => apiPost('/game/new', { seed: Date.now() & 0x7fffffff }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['gameState'] }),
  });

  if (isLoading) return <p>Loading court…</p>;
  if (!game) return (
    <div>
      <p>No game in progress.</p>
      <button onClick={() => newGame.mutate()} disabled={newGame.isPending}>
        {newGame.isPending ? 'Starting…' : 'New Game'}
      </button>
    </div>
  );
  return (
    <div className="court-view">
      <h2>Court — Year {game.year}, Week {Math.floor(game.tick / 7)}</h2>
      <p>Councilors: {game.npcs.length}</p>
      <nav>
        <Link to="/council">Council</Link> · <Link to="/">Tactical</Link>
      </nav>
    </div>
  );
}
```

If `apiPost` doesn't exist, add to `frontend/src/api/client.ts`:
```ts
export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const resp = await fetch(`/api/v1${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(`POST ${path} → ${resp.status}`);
  return resp.json();
}
```

- [ ] **Step 7: Register `/council` route**

In `App.tsx` routes block, add:
```tsx
<Route path="/council" element={<CouncilView />} />
```

Also import it.

- [ ] **Step 8: Styles**

Append to `frontend/src/styles.css`:
```css
.councilor-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }
.councilor-card { border: 1px solid #444; padding: 10px; border-radius: 6px; background: #1a1a1a; }
.councilor-card header { display: flex; justify-content: space-between; align-items: baseline; }
.councilor-card .specialty { font-size: 0.8em; opacity: 0.7; text-transform: uppercase; }
.councilor-card .stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; margin: 8px 0 0; }
.councilor-card .stats dt { font-size: 0.7em; opacity: 0.6; }
.councilor-card .stats dd { margin: 0; font-weight: bold; }
```

- [ ] **Step 9: Run tests + typecheck**

```bash
cd frontend && npx tsc --noEmit && npm test
```
Expected: all prior + 2 new passing

- [ ] **Step 10: Commit**

```bash
git add frontend/src/components/CouncilorCard.tsx frontend/src/views/CouncilView.tsx frontend/src/views/CourtView.tsx frontend/src/App.tsx frontend/src/api/client.ts frontend/src/styles.css frontend/src/components/CouncilorCard.test.tsx frontend/src/views/CouncilView.test.tsx
git commit -m "feat(frontend): CouncilorCard + CouncilView + New Game button"
```

**Phase B exit criteria:** click "New Game" at `/court` → see 5 councilors at `/council`. Full suites green.

---

## Phase C — Recruitment scene (vertical slice: open slot → scene → commit → councilor appears)

### Task 14: Engine — `tactical/scene_system.py`

**Files:**
- Create: `backend/app/engine/tactical/__init__.py` (empty)
- Create: `backend/app/engine/tactical/scene_system.py`
- Test: `backend/tests/engine/test_scene_system.py`

- [ ] **Step 1: Failing test**

```python
# backend/tests/engine/test_scene_system.py
from app.engine.tactical.scene_system import Scene, SceneBeat, advance, commit_scene

def _three_beat_scene():
    return Scene(
        id='test',
        beats=[
            SceneBeat(id='b1', text='Intro', choices=[{'id': 'next', 'text': 'Continue'}]),
            SceneBeat(id='b2', text='Middle', choices=[{'id': 'a', 'text': 'A'}, {'id': 'b', 'text': 'B'}]),
            SceneBeat(id='b3', text='Commit?', choices=[{'id': 'yes', 'text': 'Accept'}, {'id': 'no', 'text': 'Decline'}]),
        ],
        current_beat='b1',
        commit_payload={'npc_id': 42, 'slot': 'steward'},
        accept_choice_id='yes',
    )

def test_advance_moves_to_next_beat():
    s = _three_beat_scene()
    s2 = advance(s, 'next')
    assert s2.current_beat == 'b2'

def test_advance_records_branch_choice():
    s = _three_beat_scene()
    s2 = advance(s, 'next')
    s3 = advance(s2, 'a')
    assert s3.choices_made == ['next', 'a']

def test_commit_yes_returns_payload():
    s = _three_beat_scene()
    s2 = advance(s, 'next')
    s3 = advance(s2, 'a')
    result = commit_scene(s3, 'yes')
    assert result['committed'] is True
    assert result['payload']['npc_id'] == 42

def test_commit_no_returns_decline():
    s = _three_beat_scene()
    result = commit_scene(s, 'no')
    assert result['committed'] is False

def test_advance_raises_on_invalid_choice():
    import pytest
    s = _three_beat_scene()
    with pytest.raises(ValueError):
        advance(s, 'nonsense')
```

- [ ] **Step 2: Run — fail**

```bash
docker compose run --rm flask pytest backend/tests/engine/test_scene_system.py -v
```

- [ ] **Step 3: Implement**

`backend/app/engine/tactical/__init__.py`:
```python
```

`backend/app/engine/tactical/scene_system.py`:
```python
"""Reusable scene infrastructure.

First consumer: recruit_scene. Future consumers (heir_handoff, death,
marriage, digest flavor) reuse the same Scene + advance + commit API.

A Scene is a sequence of SceneBeats with per-beat choices. Each choice
either advances to the next beat or, at the terminal beat, triggers
commit with the scene's payload.
"""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SceneBeat:
    id: str
    text: str
    choices: list[dict]  # [{id: str, text: str, reveals?: {stat: value}}]


@dataclass
class Scene:
    id: str
    beats: list[SceneBeat]
    current_beat: str
    commit_payload: dict[str, Any]
    accept_choice_id: str
    choices_made: list[str] = field(default_factory=list)


def _beat(scene: Scene, beat_id: str) -> SceneBeat:
    for b in scene.beats:
        if b.id == beat_id:
            return b
    raise KeyError(beat_id)


def advance(scene: Scene, choice_id: str) -> Scene:
    beat = _beat(scene, scene.current_beat)
    if not any(c['id'] == choice_id for c in beat.choices):
        raise ValueError(f"choice {choice_id!r} not valid at beat {scene.current_beat!r}")
    idx = next(i for i, b in enumerate(scene.beats) if b.id == scene.current_beat)
    next_id = scene.beats[idx + 1].id if idx + 1 < len(scene.beats) else scene.current_beat
    return Scene(
        id=scene.id,
        beats=scene.beats,
        current_beat=next_id,
        commit_payload=scene.commit_payload,
        accept_choice_id=scene.accept_choice_id,
        choices_made=scene.choices_made + [choice_id],
    )


def commit_scene(scene: Scene, choice_id: str) -> dict:
    beat = _beat(scene, scene.current_beat)
    if not any(c['id'] == choice_id for c in beat.choices):
        raise ValueError(f"choice {choice_id!r} not valid at terminal beat")
    accepted = choice_id == scene.accept_choice_id
    return {
        'committed': accepted,
        'payload': scene.commit_payload if accepted else None,
        'choices_made': scene.choices_made + [choice_id],
    }
```

- [ ] **Step 4: Run — PASS**

```bash
docker compose run --rm flask pytest backend/tests/engine/test_scene_system.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/engine/tactical/ backend/tests/engine/test_scene_system.py
git commit -m "feat(engine): scene_system (reusable scene runner)"
```

---

### Task 15: Engine — `tactical/recruit_scene.py`

**Files:**
- Create: `backend/app/engine/tactical/recruit_scene.py`
- Test: `backend/tests/engine/test_recruit_scene.py`

- [ ] **Step 1: Failing test**

```python
# backend/tests/engine/test_recruit_scene.py
import random
from app.engine.tactical.recruit_scene import make_recruit_scene, generate_candidate

def test_candidate_has_all_four_stats():
    c = generate_candidate(rng=random.Random(1), specialty='marshal')
    for k in ('competence', 'loyalty', 'ambition', 'specialty'):
        assert k in c['stats']
    assert c['stats']['specialty'] == 'marshal'

def test_recruit_scene_is_three_beats():
    scene = make_recruit_scene(
        candidate={'id': 99, 'name': 'Rix', 'stats': {'competence': 3, 'loyalty': 3, 'ambition': 3, 'specialty': 'spy'}},
        target_slot='spy',
    )
    assert len(scene.beats) == 3
    assert scene.current_beat == scene.beats[0].id
    assert scene.commit_payload == {'candidate_id': 99, 'target_slot': 'spy'}

def test_recruit_scene_beats_reveal_stats_in_text():
    scene = make_recruit_scene(
        candidate={'id': 99, 'name': 'Rix', 'stats': {'competence': 3, 'loyalty': 4, 'ambition': 2, 'specialty': 'spy'}},
        target_slot='spy',
    )
    # Three beats surface three different stats across the dialogue
    beat_texts = ' '.join(b.text for b in scene.beats)
    assert 'Rix' in beat_texts
```

- [ ] **Step 2: Run — fail**

```bash
docker compose run --rm flask pytest backend/tests/engine/test_recruit_scene.py -v
```

- [ ] **Step 3: Implement**

`backend/app/engine/tactical/recruit_scene.py`:
```python
"""Recruit-scene generator — the first consumer of scene_system.

Per spec §2 council UX rule 1d: player meets candidate in a scene,
2–3 dialogue beats reveal 2–3 stats, player commits or declines.
"""
import random
from app.engine.tactical.scene_system import Scene, SceneBeat

_CANDIDATE_NAMES = [
    'Rix', 'Thea', 'Odo', 'Isolde', 'Garen', 'Maren', 'Silas', 'Vela',
    'Brynn', 'Cade', 'Dorin', 'Emrys', 'Faye', 'Hale',
]


def generate_candidate(rng: random.Random, specialty: str) -> dict:
    return {
        'id': rng.randint(10_000, 99_999),  # transient until commit
        'tier': 1,
        'name': rng.choice(_CANDIDATE_NAMES),
        'stats': {
            'competence': rng.randint(1, 5),
            'loyalty': rng.randint(1, 5),
            'ambition': rng.randint(1, 5),
            'specialty': specialty,
        },
        'memory': [],
        'status': 'alive',
    }


def make_recruit_scene(candidate: dict, target_slot: str) -> Scene:
    name = candidate['name']
    s = candidate['stats']
    beats = [
        SceneBeat(
            id='intro',
            text=f"{name} bows. Their bearing suggests competence of {s['competence']}.",
            choices=[{'id': 'continue', 'text': 'Ask about their past'}],
        ),
        SceneBeat(
            id='probe',
            text=(f"{name} speaks of service and loyalty {s['loyalty']}. "
                  f"Ambition flickers: {s['ambition']}."),
            choices=[
                {'id': 'continue', 'text': 'Consider the offer'},
            ],
        ),
        SceneBeat(
            id='decide',
            text=f"Will you appoint {name} as your {target_slot}?",
            choices=[
                {'id': 'accept', 'text': 'Accept'},
                {'id': 'decline', 'text': 'Decline'},
            ],
        ),
    ]
    return Scene(
        id=f'recruit:{candidate["id"]}',
        beats=beats,
        current_beat='intro',
        commit_payload={'candidate_id': candidate['id'], 'target_slot': target_slot},
        accept_choice_id='accept',
    )
```

- [ ] **Step 4: Run — PASS**

```bash
docker compose run --rm flask pytest backend/tests/engine/test_recruit_scene.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/engine/tactical/recruit_scene.py backend/tests/engine/test_recruit_scene.py
git commit -m "feat(engine): recruit_scene (3-beat dialogue, stat reveals)"
```

---

### Task 16: Service + routes — scene lifecycle

**Files:**
- Modify: `backend/app/services/game_service.py`
- Modify: `backend/app/routes/game.py`
- Modify: `backend/tests/routes/test_game_routes.py`

The scene's live state is stored in a single JSON column on `GameStateRow` — cheap, and per-session there is only ever one scene active (player is the locus). Add the column first.

- [ ] **Step 1: Alembic migration for `active_scene_json`**

```bash
docker compose run --rm flask flask db migrate -m "game_state active_scene_json"
```

Edit the generated file to add:
```python
def upgrade():
    op.add_column('game_state', sa.Column('active_scene_json', postgresql.JSONB(), nullable=True))

def downgrade():
    op.drop_column('game_state', 'active_scene_json')
```

Apply:
```bash
docker compose run --rm flask flask db upgrade
```

- [ ] **Step 2: Extend GameStateRow**

Add to `backend/app/models/game_state_row.py`:
```python
from sqlalchemy.dialects.postgresql import JSONB
# ... existing class body ...
    active_scene_json = db.Column(JSONB, nullable=True)
```

- [ ] **Step 3: Failing route tests**

Append to `backend/tests/routes/test_game_routes.py`:
```python
def test_recruit_opens_scene(client):
    client.post('/api/v1/game/new', json={'seed': 42})
    resp = client.post('/api/v1/game/recruit', json={'slot_specialty': 'marshal'})
    assert resp.status_code == 200
    body = resp.get_json()
    assert 'active_scene' in body
    assert body['active_scene']['current_beat'] == 'intro'

def test_recruit_blocked_if_slot_occupied(client):
    client.post('/api/v1/game/new', json={'seed': 42})
    # All 5 specialties are occupied by starter council
    resp = client.post('/api/v1/game/recruit', json={'slot_specialty': 'marshal'})
    assert resp.status_code == 409

def test_scene_advance_and_accept(client):
    client.post('/api/v1/game/new', json={'seed': 42})
    # Vacate marshal slot first (pretend the incumbent dies — fixture helper)
    from app.models.npc import NPC
    from app import db
    marshal = NPC.query.filter(NPC.stats_json['specialty'].astext == 'marshal').one()
    db.session.delete(marshal); db.session.commit()

    client.post('/api/v1/game/recruit', json={'slot_specialty': 'marshal'})
    client.post('/api/v1/game/scene/advance', json={'choice_id': 'continue'})
    client.post('/api/v1/game/scene/advance', json={'choice_id': 'continue'})
    resp = client.post('/api/v1/game/scene/commit', json={'choice_id': 'accept'})
    assert resp.status_code == 200
    state = resp.get_json()
    marshals = [n for n in state['npcs'] if n['stats']['specialty'] == 'marshal']
    assert len(marshals) == 1  # new councilor appointed
```

- [ ] **Step 4: Extend service**

Append to `backend/app/services/game_service.py`:
```python
import random
from app.engine.tactical.recruit_scene import make_recruit_scene, generate_candidate
from app.engine.tactical.scene_system import advance as advance_scene_engine, commit_scene
from app.engine.event_bus import Event


def _load_row():
    return db.session.get(GameStateRow, 1)


def recruit_open_slot(slot_specialty: str) -> dict:
    row = _load_row()
    if row is None:
        from werkzeug.exceptions import BadRequest
        raise BadRequest("no game in progress")
    occupied = NPC.query.filter(NPC.stats_json['specialty'].astext == slot_specialty).count()
    if occupied > 0:
        from werkzeug.exceptions import Conflict
        raise Conflict(f"slot {slot_specialty!r} already filled")
    rng = random.Random(row.tick * 1000 + hash(slot_specialty) & 0xFFFF)
    candidate = generate_candidate(rng=rng, specialty=slot_specialty)
    scene = make_recruit_scene(candidate=candidate, target_slot=slot_specialty)
    row.active_scene_json = {
        'scene_id': scene.id,
        'current_beat': scene.current_beat,
        'choices_made': scene.choices_made,
        'beats': [{'id': b.id, 'text': b.text, 'choices': b.choices} for b in scene.beats],
        'commit_payload': scene.commit_payload,
        'accept_choice_id': scene.accept_choice_id,
        'candidate': candidate,
    }
    db.session.commit()
    return {**get_state(), 'active_scene': row.active_scene_json}


def _scene_from_row_json(sj: dict):
    from app.engine.tactical.scene_system import Scene, SceneBeat
    return Scene(
        id=sj['scene_id'],
        beats=[SceneBeat(id=b['id'], text=b['text'], choices=b['choices']) for b in sj['beats']],
        current_beat=sj['current_beat'],
        commit_payload=sj['commit_payload'],
        accept_choice_id=sj['accept_choice_id'],
        choices_made=sj['choices_made'],
    )


def advance_scene(choice_id: str) -> dict:
    row = _load_row()
    if row is None or row.active_scene_json is None:
        from werkzeug.exceptions import BadRequest
        raise BadRequest("no active scene")
    scene = _scene_from_row_json(row.active_scene_json)
    next_scene = advance_scene_engine(scene, choice_id)
    row.active_scene_json = {**row.active_scene_json,
                             'current_beat': next_scene.current_beat,
                             'choices_made': next_scene.choices_made}
    db.session.commit()
    return {**get_state(), 'active_scene': row.active_scene_json}


def commit_active_scene(choice_id: str) -> dict:
    row = _load_row()
    if row is None or row.active_scene_json is None:
        from werkzeug.exceptions import BadRequest
        raise BadRequest("no active scene")
    scene = _scene_from_row_json(row.active_scene_json)
    result = commit_scene(scene, choice_id)
    if result['committed']:
        candidate = row.active_scene_json['candidate']
        npc_row = game_mappers.npc_to_row({
            **candidate, 'slot': 'council',
        })
        npc_row.id = None  # let DB assign persistent id; transient id was scene-only
        db.session.add(npc_row)
        db.session.add(game_mappers.event_to_row({
            'tick': row.tick, 'tier': 'P2',
            'source_id': None, 'source_type': 'system',
            'payload': {'kind': 'councilor_recruited',
                        'specialty': result['payload']['target_slot'],
                        'name': candidate['name']},
        }))
    else:
        db.session.add(game_mappers.event_to_row({
            'tick': row.tick, 'tier': 'P3',
            'source_id': None, 'source_type': 'system',
            'payload': {'kind': 'recruit_declined',
                        'candidate_name': row.active_scene_json['candidate']['name']},
        }))
    row.active_scene_json = None
    db.session.commit()
    return get_state()
```

- [ ] **Step 5: Extend routes**

Append to `backend/app/routes/game.py`:
```python
@bp.post('/game/recruit')
def post_recruit():
    body = request.get_json(silent=True) or {}
    slot = body.get('slot_specialty')
    if not slot:
        return {'error': "'slot_specialty' required"}, 400
    try:
        return jsonify(game_service.recruit_open_slot(slot)), 200
    except Exception as e:
        from werkzeug.exceptions import HTTPException
        if isinstance(e, HTTPException):
            return {'error': str(e.description)}, e.code
        raise


@bp.post('/game/scene/advance')
def post_scene_advance():
    body = request.get_json(silent=True) or {}
    choice = body.get('choice_id')
    if not choice:
        return {'error': "'choice_id' required"}, 400
    return jsonify(game_service.advance_scene(choice)), 200


@bp.post('/game/scene/commit')
def post_scene_commit():
    body = request.get_json(silent=True) or {}
    choice = body.get('choice_id')
    if not choice:
        return {'error': "'choice_id' required"}, 400
    return jsonify(game_service.commit_active_scene(choice)), 200
```

Also extend `game_service.get_state()` to include `active_scene`:
```python
def get_state() -> dict | None:
    row = db.session.get(GameStateRow, 1)
    if row is None:
        return None
    state = game_mappers.row_to_state(row)
    state['npcs'] = [game_mappers.row_to_npc(n) for n in NPC.query.order_by(NPC.id).all()]
    state['policies'] = [game_mappers.row_to_policy(p) for p in Policy.query.all()]
    state['active_scene'] = row.active_scene_json
    return state
```

And update `_TRUNCATE_TABLES` in `backend/tests/conftest.py`:
```python
_TRUNCATE_TABLES = 'events, agents, world_tiles, colonies, simulation_state, game_state, npcs, relationships, event_log, policies, save_meta'
```

- [ ] **Step 6: Run tests**

```bash
docker compose run --rm flask pytest backend/tests/routes/test_game_routes.py -v
```
Expected: PASS (all prior game-route tests + 3 new)

- [ ] **Step 7: Full suite**

```bash
docker compose run --rm flask pytest -q
```
Expected: 213 prior + new-game/scene tests all green

- [ ] **Step 8: Commit**

```bash
git add backend/ 
git commit -m "feat(game): scene lifecycle (recruit → advance → commit)"
```

---

### Task 17: Frontend — RecruitSceneView + recruit buttons in CouncilView

**Files:**
- Create: `frontend/src/views/RecruitSceneView.tsx`
- Modify: `frontend/src/views/CouncilView.tsx` (add recruit buttons for open slots)
- Modify: `frontend/src/api/types.ts` (add `SceneState`)
- Modify: `frontend/src/api/gameQueries.ts` (mutations for recruit/advance/commit)
- Modify: `frontend/src/App.tsx` (add /recruit route)
- Test: `frontend/src/views/RecruitSceneView.test.tsx`

- [ ] **Step 1: Extend types.ts**

Append:
```ts
export type SceneBeat = {
  id: string;
  text: string;
  choices: { id: string; text: string }[];
};

export type SceneState = {
  scene_id: string;
  current_beat: string;
  beats: SceneBeat[];
  choices_made: string[];
  commit_payload: Record<string, unknown>;
  accept_choice_id: string;
  candidate: { id: number; name: string; stats: any };
};

// Extend existing GameStateResponse:
//   active_scene: SceneState | null
```

Modify `GameStateResponse` to add `active_scene: SceneState | null`.

- [ ] **Step 2: Extend gameQueries.ts**

Append:
```ts
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiPost } from './client';

export function useRecruit() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (slot_specialty: string) => apiPost('/game/recruit', { slot_specialty }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['gameState'] }),
  });
}

export function useAdvanceScene() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (choice_id: string) => apiPost('/game/scene/advance', { choice_id }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['gameState'] }),
  });
}

export function useCommitScene() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (choice_id: string) => apiPost('/game/scene/commit', { choice_id }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['gameState'] }),
  });
}
```

- [ ] **Step 3: Implement RecruitSceneView**

`frontend/src/views/RecruitSceneView.tsx`:
```tsx
import { useGameStore } from '../store/gameStore';
import { useAdvanceScene, useCommitScene } from '../api/gameQueries';
import { useNavigate } from 'react-router-dom';

export default function RecruitSceneView() {
  const game = useGameStore((s) => s.game);
  const advance = useAdvanceScene();
  const commit = useCommitScene();
  const nav = useNavigate();

  if (!game?.active_scene) {
    return <p>No active scene.</p>;
  }
  const scene = game.active_scene;
  const beat = scene.beats.find((b) => b.id === scene.current_beat);
  if (!beat) return <p>Scene in unknown state.</p>;

  const isTerminal = scene.beats.indexOf(beat) === scene.beats.length - 1;

  const onChoice = (choiceId: string) => {
    if (isTerminal) {
      commit.mutate(choiceId, { onSuccess: () => nav('/council') });
    } else {
      advance.mutate(choiceId);
    }
  };

  return (
    <section className="scene-view">
      <article className="scene-beat">
        <p>{beat.text}</p>
        <div className="choices">
          {beat.choices.map((c) => (
            <button key={c.id} onClick={() => onChoice(c.id)}
                    disabled={advance.isPending || commit.isPending}>
              {c.text}
            </button>
          ))}
        </div>
      </article>
    </section>
  );
}
```

- [ ] **Step 4: Add /recruit route**

In `App.tsx` routes:
```tsx
<Route path="/recruit" element={<RecruitSceneView />} />
```

Import `RecruitSceneView`. In `CouncilView`, detect empty specialties and render recruit buttons that trigger the mutation and navigate:

```tsx
// in CouncilView.tsx
import { useRecruit } from '../api/gameQueries';
import { useNavigate } from 'react-router-dom';

const SPECIALTIES = ['steward', 'marshal', 'spy', 'chancellor', 'priest'] as const;

// inside component:
const recruit = useRecruit();
const nav = useNavigate();
const occupied = new Set(council.map((c) => c.stats.specialty));
const openSlots = SPECIALTIES.filter((s) => !occupied.has(s));

// render alongside the council grid:
{openSlots.length > 0 && (
  <div className="open-slots">
    <h3>Open slots</h3>
    {openSlots.map((s) => (
      <button key={s} onClick={() => recruit.mutate(s, { onSuccess: () => nav('/recruit') })}>
        Recruit {s}
      </button>
    ))}
  </div>
)}
```

- [ ] **Step 5: Failing test**

```tsx
// frontend/src/views/RecruitSceneView.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import RecruitSceneView from './RecruitSceneView';
import { useGameStore } from '../store/gameStore';

function renderWithScene() {
  useGameStore.setState({
    game: {
      tick: 0, year: 0, active_layer: 'court',
      alignment_axes: { dictator_benefactor: 0 },
      npcs: [], policies: [],
      active_scene: {
        scene_id: 'recruit:1', current_beat: 'intro',
        beats: [
          { id: 'intro', text: 'Hello', choices: [{ id: 'continue', text: 'Continue' }] },
          { id: 'decide', text: 'Accept?', choices: [{ id: 'accept', text: 'Yes' }, { id: 'decline', text: 'No' }] },
        ],
        choices_made: [], commit_payload: { target_slot: 'marshal', candidate_id: 1 },
        accept_choice_id: 'accept',
        candidate: { id: 1, name: 'Rix', stats: {} },
      },
    } as any,
    setGame: useGameStore.getState().setGame,
  });
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter><RecruitSceneView /></MemoryRouter>
    </QueryClientProvider>
  );
}

describe('RecruitSceneView', () => {
  it('renders the current beat text and choice buttons', () => {
    renderWithScene();
    expect(screen.getByText('Hello')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Continue' })).toBeInTheDocument();
  });
});
```

- [ ] **Step 6: Styles**

Append to `frontend/src/styles.css`:
```css
.scene-view { max-width: 600px; margin: 2em auto; padding: 1.5em; background: #141414; border: 1px solid #333; border-radius: 8px; }
.scene-view .choices { display: flex; gap: 12px; margin-top: 1em; }
.scene-view button { padding: 8px 16px; }
.open-slots { margin-top: 1.5em; padding: 1em; background: #1a1410; border: 1px dashed #663; border-radius: 6px; }
.open-slots button { margin-right: 8px; }
```

- [ ] **Step 7: Run tests + typecheck**

```bash
cd frontend && npx tsc --noEmit && npm test
```
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add frontend/
git commit -m "feat(frontend): recruit scene view + council recruit buttons"
```

**Phase C exit criteria:** in a running stack, start a new game → visit /council → artificially open a slot (can test by deleting a councilor via psql, or wait for Phase D's event-driven loss) → click "Recruit marshal" → complete 3-beat scene → new councilor appears on /council.

---

## Phase D — Alert attribution + quarterly digest (vertical slice: advance weeks → events attribute → digest at week 4)

### Task 18: Engine — `alert_attribution.py`

**Files:**
- Create: `backend/app/engine/alert_attribution.py`
- Test: `backend/tests/engine/test_alert_attribution.py`

- [ ] **Step 1: Failing test**

```python
# backend/tests/engine/test_alert_attribution.py
from app.engine.alert_attribution import attribute
from app.engine.event_bus import Event
from app.engine.world_state import GameState

def _state_with_councilors():
    s = GameState(seed=1)
    s.npcs[1] = {'id': 1, 'name': 'Aldric', 'tier': 1, 'slot': 'council',
                 'stats': {'competence': 2, 'loyalty': 4, 'ambition': 1, 'specialty': 'steward'}}
    return s

def test_attribution_adds_competence_to_payload():
    s = _state_with_councilors()
    ev = Event(tier='P2', tick=5, source_id=1, source_type='councilor',
               payload={'kind': 'harvest_failed', 'region': 'north'})
    attributed = attribute(ev, s)
    assert attributed.payload['source_name'] == 'Aldric'
    assert attributed.payload['source_competence'] == 2
    assert attributed.payload['source_specialty'] == 'steward'

def test_attribution_passthrough_for_system_events():
    s = _state_with_councilors()
    ev = Event(tier='P3', tick=1, source_id=None, source_type='system',
               payload={'kind': 'gossip'})
    attributed = attribute(ev, s)
    assert 'source_name' not in attributed.payload
```

- [ ] **Step 2: Run — fail**

```bash
docker compose run --rm flask pytest backend/tests/engine/test_alert_attribution.py -v
```

- [ ] **Step 3: Implement**

`backend/app/engine/alert_attribution.py`:
```python
"""Alert attribution — every strategic event surfaces its source.

Per spec §2 council UX rule 1b: "Steward Aldric failed the harvest
(Competence 2)" not "harvest failed."
"""
from app.engine.event_bus import Event
from app.engine.world_state import GameState


def attribute(event: Event, state: GameState) -> Event:
    if event.source_type != 'councilor' or event.source_id is None:
        return event
    councilor = state.npcs.get(event.source_id)
    if councilor is None:
        return event
    enriched = {
        **event.payload,
        'source_name': councilor['name'],
        'source_competence': councilor['stats'].get('competence'),
        'source_specialty': councilor['stats'].get('specialty'),
    }
    return Event(
        tier=event.tier, tick=event.tick,
        source_id=event.source_id, source_type=event.source_type,
        payload=enriched,
    )
```

- [ ] **Step 4: Run — PASS**

- [ ] **Step 5: Commit**

```bash
git add backend/app/engine/alert_attribution.py backend/tests/engine/test_alert_attribution.py
git commit -m "feat(engine): alert_attribution enriches events with source stats"
```

---

### Task 19: Engine — `council_digest.py`

**Files:**
- Create: `backend/app/engine/council_digest.py`
- Test: `backend/tests/engine/test_council_digest.py`

- [ ] **Step 1: Failing test**

```python
# backend/tests/engine/test_council_digest.py
from app.engine.council_digest import build_digest, FIRST_DIGEST_WEEK, DIGEST_INTERVAL_WEEKS
from app.engine.event_bus import Event

def test_digest_summarises_recent_events():
    events = [
        Event(tier='P2', tick=10, source_id=1, source_type='councilor',
              payload={'kind': 'harvest_failed', 'source_name': 'Aldric',
                       'source_competence': 2, 'source_specialty': 'steward'}),
        Event(tier='P3', tick=12, source_id=None, source_type='system',
              payload={'kind': 'gossip', 'text': 'Rumours from the market.'}),
        Event(tier='P3', tick=14, source_id=None, source_type='system',
              payload={'kind': 'gossip', 'text': 'Traveller tales.'}),
    ]
    digest = build_digest(events, week=4)
    assert digest['week'] == 4
    # P2 is rendered as a line; P3 collapses
    lines = digest['lines']
    assert any('Aldric' in l and 'Competence 2' in l for l in lines)
    assert any('While you were busy' in l for l in lines)

def test_digest_cadence_constants():
    assert FIRST_DIGEST_WEEK == 4
    assert DIGEST_INTERVAL_WEEKS == 12

def test_digest_is_due():
    from app.engine.council_digest import is_digest_due
    assert is_digest_due(week=4) is True
    assert is_digest_due(week=5) is False
    assert is_digest_due(week=16) is True  # 4 + 12
    assert is_digest_due(week=28) is True
    assert is_digest_due(week=17) is False
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement**

`backend/app/engine/council_digest.py`:
```python
"""Quarterly digest.

Per spec §2 council UX rule 1e: first digest fires at week 4
(frontloaded so early playtesters see it), then every 12 weeks.
5-10 councilor-attributed lines; P3 events collapse into a single
"while you were busy..." line to preserve signal.
"""
from app.engine.event_bus import Event

FIRST_DIGEST_WEEK = 4
DIGEST_INTERVAL_WEEKS = 12


def is_digest_due(week: int) -> bool:
    if week < FIRST_DIGEST_WEEK:
        return False
    if week == FIRST_DIGEST_WEEK:
        return True
    return (week - FIRST_DIGEST_WEEK) % DIGEST_INTERVAL_WEEKS == 0


def build_digest(events: list[Event], week: int) -> dict:
    lines: list[str] = []
    flavor_count = 0
    for e in events:
        if e.tier == 'P3':
            flavor_count += 1
            continue
        p = e.payload
        if e.source_type == 'councilor' and 'source_name' in p:
            lines.append(
                f"{p['source_specialty'].title()} {p['source_name']} — "
                f"{p.get('kind', 'event')} (Competence {p.get('source_competence', '?')})."
            )
        else:
            lines.append(f"{p.get('kind', 'event')} — {p.get('text', '')}".strip(' —'))
    if flavor_count > 0:
        lines.append(f"While you were busy: {flavor_count} minor goings-on.")
    return {'week': week, 'lines': lines}
```

- [ ] **Step 4: Run — PASS**

- [ ] **Step 5: Commit**

```bash
git add backend/app/engine/council_digest.py backend/tests/engine/test_council_digest.py
git commit -m "feat(engine): council_digest with week-4 frontload + 12-week cadence"
```

---

### Task 20: Engine — `advance.py` (strategic tick loop)

**Files:**
- Create: `backend/app/engine/advance.py`
- Test: `backend/tests/engine/test_advance.py`

- [ ] **Step 1: Failing test**

```python
# backend/tests/engine/test_advance.py
import random
from app.engine.advance import advance_weeks
from app.engine.new_game import new_game
from app.engine.event_bus import EventBus

def test_advance_ticks_four_weeks_and_fires_stub_events():
    state, bootstrap = new_game(seed=42)
    bus = EventBus()
    for e in bootstrap:
        bus.publish(e)

    advance_weeks(state, n=4, bus=bus, rng=random.Random(42))

    assert state.tick == 28  # 4 weeks × 7 ticks/week
    drained = bus.drain()
    # At least one P2 or P3 tick event fired from a councilor
    councilor_events = [e for e in drained if e.source_type == 'councilor']
    assert len(councilor_events) >= 1
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement**

`backend/app/engine/advance.py`:
```python
"""Strategic-tick advancement.

MVP stub: every week, each councilor rolls on a small table that either
emits a flavor/social event or is silent. Attribution tags the event so
the digest can render "Steward Aldric failed the harvest (Competence 2)"
instead of "harvest failed."
"""
import random
from app.engine.world_state import GameState
from app.engine.event_bus import Event, EventBus
from app.engine.alert_attribution import attribute

TICKS_PER_WEEK = 7


def _roll_councilor_event(councilor: dict, rng: random.Random, tick: int) -> Event | None:
    roll = rng.random()
    if roll < 0.4:
        return None  # silent
    competence = councilor['stats']['competence']
    specialty = councilor['stats']['specialty']
    if roll < 0.7:
        kind = f"{specialty}_success" if competence >= 3 else f"{specialty}_stumble"
        tier = 'P3'
    else:
        kind = f"{specialty}_report"
        tier = 'P2'
    return Event(
        tier=tier, tick=tick,
        source_id=councilor['id'], source_type='councilor',
        payload={'kind': kind},
    )


def advance_weeks(state: GameState, n: int, bus: EventBus, rng: random.Random) -> None:
    for _ in range(n):
        for _ in range(TICKS_PER_WEEK):
            state.tick += 1
        # One roll per councilor per week, at end of week
        for npc in state.npcs.values():
            if npc.get('slot') != 'council' or npc.get('status') != 'alive':
                continue
            ev = _roll_councilor_event(npc, rng, state.tick)
            if ev is not None:
                bus.publish(attribute(ev, state))
    # Update year if we've crossed a 52-week boundary (stub)
    state.year = state.tick // (TICKS_PER_WEEK * 52)
```

- [ ] **Step 4: Run — PASS**

- [ ] **Step 5: Commit**

```bash
git add backend/app/engine/advance.py backend/tests/engine/test_advance.py
git commit -m "feat(engine): advance_weeks stub tick loop with councilor rolls"
```

---

### Task 21: Service + route — `POST /api/v1/game/advance`

**Files:**
- Modify: `backend/app/services/game_service.py`
- Modify: `backend/app/routes/game.py`
- Modify: `backend/tests/routes/test_game_routes.py`

- [ ] **Step 1: Failing test**

Append to `backend/tests/routes/test_game_routes.py`:
```python
def test_advance_4_weeks_surfaces_digest(client):
    client.post('/api/v1/game/new', json={'seed': 42})
    resp = client.post('/api/v1/game/advance', json={'weeks': 4})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['tick'] == 28
    assert 'digest' in body
    assert body['digest'] is not None
    assert body['digest']['week'] == 4
    assert len(body['digest']['lines']) >= 1

def test_advance_1_week_no_digest(client):
    client.post('/api/v1/game/new', json={'seed': 42})
    resp = client.post('/api/v1/game/advance', json={'weeks': 1})
    body = resp.get_json()
    assert body['digest'] is None
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Extend service**

Append to `backend/app/services/game_service.py`:
```python
from app.engine.advance import advance_weeks, TICKS_PER_WEEK
from app.engine.event_bus import EventBus
from app.engine.council_digest import build_digest, is_digest_due
from app.engine.world_state import GameState


def _hydrate_state() -> GameState:
    row = _load_row()
    state = GameState(
        seed=1, tick=row.tick, year=row.year,
        active_layer=row.active_layer,
        alignment_axes=row.alignment_axes_json,
    )
    for n_row in NPC.query.all():
        npc = game_mappers.row_to_npc(n_row)
        # Stash slot in the dict — not a real column, per-tier convention
        npc['slot'] = 'council' if npc['tier'] == 1 else None
        state.npcs[npc['id']] = npc
    return state


def advance(weeks: int) -> dict:
    row = _load_row()
    if row is None:
        from werkzeug.exceptions import BadRequest
        raise BadRequest("no game in progress")
    state = _hydrate_state()
    bus = EventBus()
    advance_weeks(state, n=weeks, bus=bus, rng=random.Random(row.tick + weeks))
    drained = bus.drain()

    row.tick = state.tick
    row.year = state.year
    for ev in drained:
        db.session.add(game_mappers.event_to_row({
            'tick': ev.tick, 'tier': ev.tier,
            'source_id': ev.source_id, 'source_type': ev.source_type,
            'payload': ev.payload,
        }))

    week = state.tick // TICKS_PER_WEEK
    digest = None
    if is_digest_due(week):
        # Collect all P0/P1/P2 events since last digest (MVP: since week 0)
        since_tick = max(0, state.tick - TICKS_PER_WEEK * (4 if week == 4 else 12))
        logged_events = [
            game_mappers.row_to_event(r)
            for r in EventLog.query.filter(
                EventLog.tick >= since_tick,
                EventLog.tier.in_(['P2', 'P3']),
            ).order_by(EventLog.tick).all()
        ]
        from app.engine.event_bus import Event as _E
        digest = build_digest(
            [_E(tier=e['tier'], tick=e['tick'], source_id=e['source_id'],
                source_type=e['source_type'], payload=e['payload'])
             for e in logged_events],
            week=week,
        )
    db.session.commit()
    return {**get_state(), 'digest': digest}
```

- [ ] **Step 4: Extend route**

Append to `backend/app/routes/game.py`:
```python
@bp.post('/game/advance')
def post_advance():
    body = request.get_json(silent=True) or {}
    weeks = body.get('weeks', 1)
    if not isinstance(weeks, int) or weeks < 1 or weeks > 52:
        return {'error': "'weeks' must be int in [1, 52]"}, 400
    return jsonify(game_service.advance(weeks)), 200
```

- [ ] **Step 5: Run**

```bash
docker compose run --rm flask pytest backend/tests/routes/test_game_routes.py -v
```
Expected: PASS

- [ ] **Step 6: Full suite**

```bash
docker compose run --rm flask pytest -q
```

- [ ] **Step 7: Commit**

```bash
git add backend/
git commit -m "feat(game): POST /advance ticks weeks + returns digest at week 4/16/28…"
```

---

### Task 22: Frontend — DigestModal + CourtView "advance" control

**Files:**
- Create: `frontend/src/components/DigestModal.tsx`
- Modify: `frontend/src/views/CourtView.tsx`
- Modify: `frontend/src/api/gameQueries.ts`
- Modify: `frontend/src/api/types.ts`
- Test: `frontend/src/components/DigestModal.test.tsx`

- [ ] **Step 1: Types**

Append to `types.ts`:
```ts
export type Digest = {
  week: number;
  lines: string[];
};
```

- [ ] **Step 2: Mutation**

Append to `gameQueries.ts`:
```ts
import { useState } from 'react';

export function useAdvance() {
  const qc = useQueryClient();
  const [lastDigest, setLastDigest] = useState<any>(null);
  const mut = useMutation({
    mutationFn: (weeks: number) => apiPost<any>('/game/advance', { weeks }),
    onSuccess: (data) => {
      setLastDigest(data.digest ?? null);
      qc.invalidateQueries({ queryKey: ['gameState'] });
    },
  });
  return { ...mut, lastDigest, clearDigest: () => setLastDigest(null) };
}
```

- [ ] **Step 3: DigestModal component**

```tsx
// frontend/src/components/DigestModal.tsx
import type { Digest } from '../api/types';

export default function DigestModal({ digest, onClose }: { digest: Digest; onClose: () => void }) {
  return (
    <div className="digest-modal-backdrop" role="dialog" aria-labelledby="digest-title">
      <div className="digest-modal">
        <h2 id="digest-title">Council Digest — Week {digest.week}</h2>
        <ul>
          {digest.lines.map((l, i) => <li key={i}>{l}</li>)}
        </ul>
        <button onClick={onClose}>Acknowledged</button>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Wire DigestModal into CourtView**

```tsx
// CourtView.tsx — add
import { useAdvance } from '../api/gameQueries';
import DigestModal from '../components/DigestModal';

// inside component:
const advance = useAdvance();

// in JSX after the game-state render:
<button onClick={() => advance.mutate(4)} disabled={advance.isPending}>
  Advance 4 weeks
</button>
{advance.lastDigest && <DigestModal digest={advance.lastDigest} onClose={advance.clearDigest} />}
```

- [ ] **Step 5: Failing test**

```tsx
// frontend/src/components/DigestModal.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import DigestModal from './DigestModal';

describe('DigestModal', () => {
  it('renders lines and fires onClose', () => {
    const onClose = vi.fn();
    render(<DigestModal digest={{ week: 4, lines: ['line A', 'line B'] }} onClose={onClose} />);
    expect(screen.getByText('line A')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Acknowledged'));
    expect(onClose).toHaveBeenCalled();
  });
});
```

- [ ] **Step 6: Styles**

Append:
```css
.digest-modal-backdrop { position: fixed; inset: 0; background: rgba(0,0,0,0.7); display: flex; align-items: center; justify-content: center; z-index: 100; }
.digest-modal { background: #1a1a1a; border: 1px solid #555; padding: 1.5em 2em; border-radius: 8px; max-width: 500px; width: 90%; }
.digest-modal ul { margin: 1em 0; padding-left: 1em; }
.digest-modal li { margin: 6px 0; }
```

- [ ] **Step 7: Run tests + typecheck**

```bash
cd frontend && npx tsc --noEmit && npm test
```

- [ ] **Step 8: Commit**

```bash
git add frontend/
git commit -m "feat(frontend): DigestModal + Advance 4 weeks control"
```

**Phase D exit criteria:** in a running stack, new game → click "Advance 4 weeks" on /court → DigestModal appears with ≥1 councilor-attributed line. Acknowledge → modal closes.

---

## Phase E — Integration test + verify

### Task 23: Backend integration test — full Foundation arc

**Files:**
- Create: `backend/tests/integration/test_foundation_arc.py`

- [ ] **Step 1: Write the integration test**

```python
# backend/tests/integration/test_foundation_arc.py
"""Full Foundation arc: new game → open a slot → recruit → advance 4 weeks → digest."""
from app.models.npc import NPC
from app import db


def test_full_foundation_arc(client):
    # 1. New game
    r = client.post('/api/v1/game/new', json={'seed': 42})
    assert r.status_code == 201
    state = r.get_json()
    assert len(state['npcs']) == 5

    # 2. Open the marshal slot (spec says: grave-wound/death content not in MVP,
    #    but tests can manipulate the DB directly to simulate an open slot).
    marshal = NPC.query.filter(NPC.stats_json['specialty'].astext == 'marshal').one()
    db.session.delete(marshal); db.session.commit()

    # 3. Start a recruit scene
    r = client.post('/api/v1/game/recruit', json={'slot_specialty': 'marshal'})
    assert r.status_code == 200
    assert r.get_json()['active_scene']['current_beat'] == 'intro'

    # 4. Advance through beats
    r = client.post('/api/v1/game/scene/advance', json={'choice_id': 'continue'})
    assert r.status_code == 200
    r = client.post('/api/v1/game/scene/advance', json={'choice_id': 'continue'})
    assert r.status_code == 200

    # 5. Commit with accept
    r = client.post('/api/v1/game/scene/commit', json={'choice_id': 'accept'})
    state = r.get_json()
    marshals = [n for n in state['npcs'] if n['stats']['specialty'] == 'marshal']
    assert len(marshals) == 1

    # 6. Advance 4 weeks → digest fires
    r = client.post('/api/v1/game/advance', json={'weeks': 4})
    body = r.get_json()
    assert body['digest'] is not None
    assert body['digest']['week'] == 4

    # 7. Shape contract: ensure existing /world/state endpoint still works
    r = client.get('/api/v1/world/state')
    assert r.status_code in (200, 404)  # 404 if no colony sim ever started; not 500
```

- [ ] **Step 2: Run**

```bash
docker compose run --rm flask pytest backend/tests/integration/test_foundation_arc.py -v
```
Expected: PASS

- [ ] **Step 3: Full backend suite — final green**

```bash
docker compose run --rm flask pytest -q
```
Expected: 213 prior + all new = 100% green.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/integration/test_foundation_arc.py
git commit -m "test(integration): full Foundation arc (new game → recruit → advance → digest)"
```

---

### Task 24: Manual verification checklist

- [ ] **Step 1: Bring the stack up**

```bash
docker compose up -d --build
```

- [ ] **Step 2: Run this checklist in a browser at http://localhost**

Each item must pass before the Foundation is declared shipped. Screenshot or make a note on anything that fails; fix and re-run.

- [ ] `GET /api/v1/world/state` (via curl) responds — either `200` or `404`, not `500`. (Regression check.)
- [ ] Root `/` shows tactical canvas as before. Existing colony-sim UX unchanged.
- [ ] Nav "Court" link visits `/court` successfully.
- [ ] `/court` shows "No game in progress" + "New Game" button.
- [ ] Click "New Game" → page shows `Year 0, Week 0` + `Councilors: 5`.
- [ ] Click "Council" → see 5 CouncilorCards, one per specialty.
- [ ] Each card shows Competence / Loyalty / Ambition numerically + specialty label.
- [ ] At least one councilor per specialty has Competence ≥ 3 (forgiving-first-run rule).
- [ ] Simulate an open slot via psql: `docker compose exec db psql -U tunnels -c "delete from npcs where stats_json->>'specialty'='marshal';"` — reload council, should see "Open slots: Recruit marshal".
- [ ] Click "Recruit marshal" → `/recruit` view opens with 3-beat scene (intro → probe → decide).
- [ ] Click "Continue" twice, then "Accept" → redirected to `/council` with marshal slot filled by new councilor.
- [ ] Back on `/court`, click "Advance 4 weeks" → DigestModal appears with Week 4 header + ≥1 line.
- [ ] DigestModal "Acknowledged" button closes modal.
- [ ] Browser console shows no React errors and no failed network requests.
- [ ] `curl -sI http://localhost/api/v1/game/state` twice in a row: second response shows `X-Cache-Status: HIT`.

- [ ] **Step 3: If all green, final commit (if anything was touched during verification)**

```bash
git status
# any fixups? commit them; otherwise nothing to commit.
```

- [ ] **Step 4: Bump docs**

Append to `STUDY_NOTES.md` (if present) or create `docs/FOUNDATION_SHIPPED.md`:
```
Foundation (Sub-project A) shipped 2026-04-17.
Tests: 213 backend + <new> = <total> / 37 frontend + <new> = <total>
Next: Sub-project B (tactical combat) — depends on world_state + tactical.py scaffolding from A.
```

Commit.

---

## Self-review summary

**Spec coverage audit (vs. `2026-04-17-tunnels-vision-design.md`):**

- §2 NPC tiering (T1 memory + stats) → Task 1 (NPC model) ✓
- §2 Event log retention (P0-P3) → Tasks 1, 4, 19, 20 ✓ (log retention pruning is Future-Us; MVP keeps all)
- §2 Persistence schema (game_state, npcs, event_log, policies, save_meta) → Task 1 ✓
- §2 Scene system → Task 14 ✓
- §2 Council UX 1a-1e → Tasks 11 (1c), 13 (1a), 15 (1d), 17 (1d), 18 (1b), 19 (1e) ✓
- §2 Flask route boundary (`/api/v1/game/*` new; `/world/state` unchanged) → Task 6 + Task 23 regression check ✓
- §2 Frontend route-level switching → Task 9 ✓
- §2 Zustand store hydrated from /api/v1/game/state → Task 8 ✓
- §2 nginx cache block → Task 10 ✓
- §3 MVP starter council 5 slots → Task 11 ✓
- Non-negotiable #5 (council legible + attributable) → Tasks 13, 18, 19 ✓

**Not in this plan (deferred to later sub-projects, by design):**
- Tactical combat loop (Sub-project B)
- Life-sim schedule slots (Sub-project C)
- Policy effects + strategic tick economics (Sub-project D)
- Content (10 event chains, 3 nodes, epilogues) (Sub-project F)
- SQLite switch (spec says deferred to build time; Postgres is fine for MVP)
- Twilight UI (Sub-project C dependency — needs age mechanics)

**Placeholder scan:** no TBDs remaining. Task 24 is a user-visible checklist, not a placeholder.

**Type consistency:** `GameState` attribute names (`tick`, `year`, `npcs`, `policies`, `alignment_axes`) match between `world_state.py`, mappers, service, routes, frontend types. `Councilor` frontend type matches the engine `{id, tier, name, stats, memory, status}` shape. Scene fields (`scene_id`, `current_beat`, `beats`, `choices_made`, `commit_payload`, `accept_choice_id`, `candidate`) are identical in engine `Scene` dataclass, service serialisation, `SceneState` TS type, and `RecruitSceneView` consumption.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-17-tunnels-foundation.md`. Two execution options:

**1. Subagent-Driven (recommended)** — fresh subagent per task, review between tasks, fast iteration. Best for a plan this size (24 tasks across 5 phases).

**2. Inline Execution** — execute tasks in this session using executing-plans, batch execution with checkpoints for review. Better if you want to watch each task happen live and intervene.

**Which approach?**
