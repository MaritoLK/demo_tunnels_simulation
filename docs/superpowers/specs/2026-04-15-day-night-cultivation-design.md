# Day/Night Cycle + Multi-Colony Cultivation — Design

**Date:** 2026-04-15 (revised post-critique same day)
**Target demo:** BUUK Infrastructure interview, 2026-04-17
**Scope:** Narrow — two polished subsystems on top of the existing colony sim.

## Goals

Transform the current single-colony foraging sim into a multi-colony survival loop driven by a diurnal rhythm. Interview pitch:

> *Four colonies share a depleting map. A daily cycle dictates when they wake, work, return home, and sleep. Wild food alone is insufficient — only colonies that cultivate in time survive.*

## Non-goals

Explicitly deferred (interviewer-addressable as "what I'd build next"):

- Enemy agents / combat
- Weather system
- Crafting / items / inventory
- Tile ownership or territory rules
- Built structures (shelters, fences)

Competition between colonies is emergent from shared scarcity, not modelled as conflict.

## Architecture

No layer changes. New logic slots into existing three-tier layout:

```
routes/  → services/  → engine/ + models/ → PostgreSQL
```

- `engine/cycle.py` — new pure module: phase/day math, no I/O
- `engine/agent.py` — priority chain extended for plant/harvest + phase wiring
- `engine/simulation.py` — `Simulation.step()` calls `world.tick(phase)` after the agent loop (single, documented insertion point)
- `services/simulation_service.py` — multi-colony spawn, event-driven colony-stock accounting
- `routes/simulation.py` — `/world/state` response gains `colonies` + `sim.day` + `sim.phase`
- `models.py` — new `Colony` table, additive columns on `Agent`, `WorldTile`

Engine stays pure (no Flask, no DB). All colony-stock mutations happen in the service layer, driven by event payloads the engine emits — mirrors the dirty-tile pattern (§9.19).

## Data model

### New table `colonies`

| column       | type        | notes                                           |
|--------------|-------------|-------------------------------------------------|
| `id`         | PK int      |                                                 |
| `name`       | str         | e.g. "Red", "Blue"                              |
| `color`      | str(7)      | hex `#rrggbb`, for UI tinting                   |
| `camp_x`     | int         | fixed position, inset from corner               |
| `camp_y`     | int         | fixed position, inset from corner               |
| `food_stock` | int         | NOT NULL, default 0, server_default '0'; starts at `INITIAL_FOOD_STOCK` on spawn |

### `agents` — new column

- `colony_id` FK → `colonies.id`, nullable at the schema level. The migration also `DELETE`s all existing rows from `agents` and `world_tiles` so no NULL `colony_id` rows survive into runtime. Rationale: this project is pre-demo and has no production data; a dev-only wipe avoids backfill gymnastics while keeping the frontend sprite tint lookup safe (no `undefined.color` crash path).

### `world_tiles` — new columns

- `crop_state` enum: `none` | `growing` | `mature` (default `none`)
- `crop_growth_ticks` int default 0

Wild tile `resource_amount` initial values lowered at seed time — no schema change, only config.

### `simulation_state` — no change

`day` and `phase` are derived from `current_tick`:

```python
TICKS_PER_DAY = 120
TICKS_PER_PHASE = 30
PHASES = ('dawn', 'day', 'dusk', 'night')

day   = current_tick // TICKS_PER_DAY
phase = PHASES[(current_tick % TICKS_PER_DAY) // TICKS_PER_PHASE]
```

Pure function of `current_tick`, which is durable (persisted on `SimulationState`). After reload, phase is consistent — no drift across restarts.

**Wall-time caveat:** the "1 day = 60s" framing assumes `sim.speed == 1` (2 ticks/s). Variable speed (existing knob) rescales wall-time but not in-game phase semantics. `ClockWidget` displays phase/day from `sim.tick` only — it never reads wall time. Demo runs at `speed=1`.

## Cycle constants

- **120 ticks/day**, split 30-30-30-30 across dawn → day → dusk → night
- At 2 ticks/s server cadence (`speed=1`), one day = 60s of wall time
- A 5-min interview demo covers ~5 in-game days

## Phase scheduler

`engine/simulation.py` gets one new call after the agent loop:

```python
def step(self):
    # existing per-agent tick loop
    for agent in self.agents:
        events.extend(tick_agent(agent, self.world, self.agents, rng=...))
    # new: world-level per-tick logic (crop growth, colony rollups)
    events.extend(self.world.tick(cycle.phase_for(self.current_tick)))
    self.current_tick += 1
    return events
```

`world.tick(phase)` only does work during `'day'` — increments `crop_growth_ticks` on every `growing` tile and emits `crop_matured` for any that cross 60. One insertion point, event-driven, testable in isolation.

## Phase behavior table

| Phase   | Ticks  | Per-agent action                                                                             |
|---------|--------|----------------------------------------------------------------------------------------------|
| dawn    | 0–29   | On camp + `food_stock >= EAT_COST` + `hunger < NEED_MAX` + not-yet-eaten-this-dawn: emit `ate_from_cache`. Else step toward camp. |
| day     | 30–59  | Extended `decide_action` chain — see below.                                                  |
| dusk    | 60–89  | Greedy Manhattan step toward own `camp_x, camp_y`.                                           |
| night   | 90–119 | No action. Hunger decay halved (`HUNGER_DECAY * NIGHT_HUNGER_SCALE`).                        |

### Day-phase action priority (extended `decide_action`)

The existing priority chain (health-crit → hunger-crit → energy-crit → hunger-mod → social-low → explore) is preserved. New branches slot in at well-defined points — **phase is an input to `decide_action`, not a separate controller**:

```python
def decide_action(agent, world, colony, phase):
    # survival first (unchanged)
    if agent.health < HEALTH_CRITICAL:
        return 'rest' if agent.energy < ENERGY_CRITICAL else 'forage'
    if agent.hunger < HUNGER_CRITICAL:
        return 'forage'   # includes wild food + mature crops on-tile
    if agent.energy < ENERGY_CRITICAL:
        return 'rest'

    # day-phase productive actions
    if phase == 'day':
        tile = world.tile_at(agent.x, agent.y)
        if tile.crop_state == 'mature':
            return 'harvest'                                      # new
        if tile.crop_state == 'none' and tile.resource_amount == 0 \
           and colony.growing_count < MAX_FIELDS_PER_COLONY:
            return 'plant'                                        # new

    # existing chain tail
    if agent.hunger < HUNGER_MODERATE:
        return 'forage'
    if agent.social < SOCIAL_LOW:
        return 'socialise'
    return 'explore'
```

Key properties:
- **Mutually exclusive branches.** A `growing` tile (`resource_amount == 0`, `crop_state == 'growing'`) falls through the plant check because `crop_state != 'none'`. No replant-on-itself bug.
- **Harvest is a distinct action**, not overloaded forage. Emits its own event. Wild forage behavior unchanged.
- **`colony.growing_count`** is a service-computed scalar injected into the engine per-tick (via the same per-agent `all_agents`-style parameter plumbing). Keeps the engine pure — it reads the count, doesn't query DB.
- **Deterministic given seed** — same inputs, same decision.

### Plant action

- Pre-condition: on empty wild tile, day phase, colony has room (`growing_count < MAX_FIELDS_PER_COLONY`)
- Effect: `tile.crop_state = 'growing'`, `tile.crop_growth_ticks = 0`
- Event: `planted {agent_id, tile_x, tile_y, colony_id}`
- No hunger/energy cost in v1 (keeps balance math predictable; can add later)

### Harvest action

- Pre-condition: on `mature` tile, day phase
- Effect: credit `colony.food_stock += HARVEST_YIELD` (done by service from event payload), reset tile to `crop_state = 'none'`, `crop_growth_ticks = 0`, `resource_amount = 0`
- Event: `harvested {agent_id, tile_x, tile_y, colony_id, yield_amount}`
- The harvester's colony gets the credit (not the planter's) — matches the "pure scarcity, no ownership" rule user approved in brainstorming.

### Crop growth (world tick, day phase only)

```python
# engine/world.py
def tick(self, phase):
    if phase != 'day':
        return []
    events = []
    for tile in self.growing_tiles():
        tile.crop_growth_ticks += 1
        if tile.crop_growth_ticks >= CROP_MATURE_TICKS:
            tile.crop_state = 'mature'
            tile.resource_amount = HARVEST_YIELD
            events.append({'type': 'crop_matured', 'data': {'tile_x': tile.x, 'tile_y': tile.y}})
    return events
```

60 day-phase ticks = 2 in-game days of daylight.

### Eat at camp (dawn phase, once per agent per day)

- Pre-condition: agent on own camp tile, `phase == 'dawn'`, colony `food_stock >= EAT_COST`, `agent.hunger < NEED_MAX`, agent has not already eaten this dawn window.
- Effect: cap-fill hunger — `agent.hunger = NEED_MAX`. Agent flagged as "ate this dawn" (transient tick-scoped marker, cleared when `phase != 'dawn'`).
- Event: `ate_from_cache {agent_id, colony_id, amount: EAT_COST, hunger_before, hunger_after}`
- Service reads `amount` from event payload and applies `colony.food_stock -= amount` — engine never touches DB-owned state. Same pattern as harvest.
- **Why cap-fill, not fixed `EAT_RESTORE`:** balance math assumes one meal perfectly replaces the ~52.5 hunger lost per day. Cap-fill is the cleanest way to encode "a meal = a full belly" without tuning a separate restore constant. Agents who wild-foraged the previous day arrive at dawn already near full → `hunger < NEED_MAX` check fails → they skip eating → stock is spared.

### Stranded-at-night behavior

Agents who don't reach camp by end of dusk:
- Night phase: they **sleep in place** (no action). Hunger decay is halved same as camp sleepers — sleeping under the stars is slightly less efficient narrative-wise but mechanically identical. Simpler than a two-tier sleep model.
- Dawn phase: `ate_from_cache` gate requires on-camp-tile, so stranded agents skip dawn eat. They step toward camp during dawn (off-camp branch of dawn rule). They eat the *following* dawn if they make it home.
- This creates natural pressure: agents that over-explore miss a meal.

## New events

| type              | data keys                                                              |
|-------------------|------------------------------------------------------------------------|
| `planted`         | `agent_id, tile_x, tile_y, colony_id`                                  |
| `crop_matured`    | `tile_x, tile_y`                                                       |
| `harvested`       | `agent_id, tile_x, tile_y, colony_id, yield_amount`                    |
| `ate_from_cache`  | `agent_id, colony_id, amount, hunger_before, hunger_after`             |

`slept` event **cut** — YAGNI, noise in log.

All flow through the existing event persistence pipe (§9.17, §9.32).

## Service layer changes

### `create_simulation` signature

```python
def create_simulation(
    width=20, height=20, seed=...,
    colonies=4, agents_per_colony=3,
):
```

- Spawns `N` `Colony` rows at fixed camp positions inset 3 tiles from each corner: `(3,3)`, `(w-4,3)`, `(3,h-4)`, `(w-4,h-4)`. For 20×20: `(3,3), (16,3), (3,16), (16,16)`.
- Distinct colors: red `#e74c3c`, blue `#3498db`, green `#2ecc71`, yellow `#f1c40f`.
- Spawns `agents_per_colony` agents per colony at the camp tile.
- Initializes `food_stock = INITIAL_FOOD_STOCK` per colony.
- Wild tile resource seeding: density ≥ 20% of tiles start with `resource_amount > 0`, amount uniform in `[1, WILD_RESOURCE_MAX]`. Enforce a local density floor: each camp must have ≥3 wild food tiles within a 5-tile radius at seed time (guards open risk #1).

### Event → DB wiring (service layer, post-step)

After `sim.run(ticks)`, the service walks the returned event list and applies DB-side mutations:

| event            | mutations                                                                              |
|------------------|----------------------------------------------------------------------------------------|
| `planted`        | update `WorldTile.crop_state = 'growing'`, `crop_growth_ticks = 0`                     |
| `crop_matured`   | update `WorldTile.crop_state = 'mature'`, `resource_amount = HARVEST_YIELD`            |
| `harvested`      | `WorldTile.crop_state = 'none'`, `crop_growth_ticks = 0`, `resource_amount = 0`; `Colony.food_stock += yield_amount` |
| `ate_from_cache` | `Colony.food_stock -= amount`                                                          |
| `foraged`        | existing dirty-tile pipe (§9.19)                                                       |

Colony rows mutated this way form a **dirty-colony set** (analogous to §9.19's dirty-tile set). One `UPDATE` per colony per step, not per event — SQLAlchemy session tracks it.

### Removed-fn callout

**No `eat_at_camp(agent, colony)` service function.** Earlier sketch was wrong — it straddled engine/service. The engine mutates `agent.hunger` as part of the agent tick and emits `ate_from_cache`; the service applies `food_stock` decrement from event payload. Symmetric with `harvested`.

## Route changes

`GET /api/v1/world/state` response gains:

```json
{
  "sim": {
    "tick": 342,
    "day": 2,
    "phase": "dusk",
    "running": true,
    "speed": 1
  },
  "colonies": [
    {"id": 1, "name": "Red",    "color": "#e74c3c", "camp_x": 3,  "camp_y": 3,  "food_stock": 47, "growing_count": 2},
    {"id": 2, "name": "Blue",   "color": "#3498db", "camp_x": 16, "camp_y": 3,  "food_stock": 58, "growing_count": 3},
    {"id": 3, "name": "Green",  "color": "#2ecc71", "camp_x": 3,  "camp_y": 16, "food_stock": 12, "growing_count": 1},
    {"id": 4, "name": "Yellow", "color": "#f1c40f", "camp_x": 16, "camp_y": 16, "food_stock": 0,  "growing_count": 0}
  ],
  "world": { "tiles": [ ... each tile now includes crop_state, crop_growth_ticks ... ] },
  "agents": [ { ..., "colony_id": 1 } ],
  "events": [ ... ]
}
```

`growing_count` is **authoritative at step boundaries, mutable within a step**. `Simulation.step()` begins by recomputing each colony's count from `world.tiles` (count of `crop_state='growing' AND crop_colony_id=colony.id`). During the step's agent loop, `plant()` increments the local counter so agents iterating later in the same tick see the fresh value and respect the field cap; `harvest()` does *not* touch any counter — the next step's recompute will reflect the freed slot on the planter's side.

Why: if the counter only ever incremented (current T7 behaviour pre-fix) then a colony whose crops got stolen would be locked out of planting forever (`growing_count` stuck at MAX while their tiles sit empty). The step-start recompute eliminates that lock-out. Keeping in-step mutation avoids the subtler "two agents plant the same tick, both think they have room" double-plant.

nginx micro-cache (§9.27d) keeps the per-sim 1s cache unchanged.

## Frontend

### New `ClockWidget` (top-right HUD)

Reads `sim.day`, `sim.phase`, and `sim.tick % 30` for phase progress:

```
☀ Day 3 · Dusk
▓▓▓▓▓▓░░░░  18/30
```

~40 lines of React + CSS.

### Phase tint overlay

Absolute-positioned div over the map canvas, class `phase-{phase}`. CSS-only, 1s transition on class change:

| phase | overlay color                 |
|-------|-------------------------------|
| dawn  | `rgba(255, 165,  80, 0.15)`   |
| day   | `rgba(  0,   0,   0, 0.00)`   |
| dusk  | `rgba(150,  80, 180, 0.20)`   |
| night | `rgba( 20,  30,  80, 0.45)`   |

### Agent sprite tint

Agent renderer looks up `colony = colonyById[agent.colony_id]`, applies `colony.color` as `fill` / CSS filter.

### Camp tile rendering — simplified

**Colored square at `(camp_x, camp_y)` in `colony.color`.** No tent sprite, no asset pipeline. Save the asset work for post-demo polish.

### Crop tile rendering — simplified

**Binary states**, no growth scaling:
- `growing` — single sprout sprite (or simple green dot), uniform size regardless of `crop_growth_ticks`
- `mature` — full crop sprite (or bright yellow dot)

Saves an asset + a per-tick sprite-scale calculation + a cross-browser SVG transform path.

### Food stock + growing count readout

Small bottom-of-HUD panel, one row per colony:

```
Red   ████░░░░  food 47   fields 2
Blue  █████░░░  food 58   fields 3
Green █░░░░░░░  food 12   fields 1
Yellow ░░░░░░░░ food 0    fields 0
```

Interviewer sees the stocks diverge in real time — the competition story in a glance.

### Store changes

No new client-side stores. Colonies, phase, and growing_count come from server in `/world/state`. Existing `useViewStore` unchanged (the `paused` cleanup commit applies).

## Migrations

One Alembic migration, all additive + dev-only data wipe:

1. Create `colonies` table
2. `DELETE FROM world_tiles; DELETE FROM agents;` — dev-only wipe, pre-demo only, documented in migration docstring
3. `agents`: add `colony_id` nullable FK column
4. `world_tiles`: add `crop_state` + `crop_growth_ticks` columns with defaults

**Test clean-slate migration today:** `docker compose down -v && docker compose up` + `flask db upgrade` + sanity run. Do this Wednesday, not Friday.

## Balance parameters

Rerun with real engine constants (`needs.py:HUNGER_DECAY=0.5`, `FORAGE_HUNGER_RESTORE=30`, `FORAGE_TILE_DEPLETION=5`, `NEED_MAX=100`, `HUNGER_MODERATE=50`, `HUNGER_CRITICAL=20`).

| constant                   | value | rationale                                                              |
|----------------------------|-------|------------------------------------------------------------------------|
| `TICKS_PER_DAY`            | 120   | fixed by design                                                        |
| `TICKS_PER_PHASE`          | 30    | fixed by design                                                        |
| `NIGHT_HUNGER_SCALE`       | 0.5   | halves `HUNGER_DECAY` at night                                         |
| `CROP_MATURE_TICKS`        | 60    | 2 in-game days of daylight                                             |
| `HARVEST_YIELD`            | 9     | one mature crop = 9 food_stock units — funds ~1.5 dawn-meals for a colony |
| `INITIAL_FOOD_STOCK`       | 18    | 3 agents × 6 = 18 stock = exactly 1 day of full camp reliance (see math below) |
| `EAT_COST`                 | 6     | each `ate_from_cache` deducts 6 from food_stock                        |
| `EAT_RESTORE`              | `NEED_MAX - agent.hunger` (cap-fill) | fills to full; one meal/agent/day is enough |
| `WILD_RESOURCE_MAX`        | 5     | lowered; one forage (depletion=5) empties a wild tile                  |
| `WILD_TILE_DENSITY`        | 0.15  | 15% of tiles seed with wild food; total wild food ≈ `0.15 × 400 × avg(3) = 180` units on 20×20 map |
| `MAX_FIELDS_PER_COLONY`    | 4     | caps `growing_count` to keep balance tractable + UI readable            |
| `DAWN_EAT_ONCE_PER_AGENT`  | true  | hard cap: each agent eats at most once per dawn window                  |

### Demand vs supply math (12 agents, 4 colonies × 3)

- **Hunger lost per agent per day** = `(90 awake ticks × 0.5) + (30 night ticks × 0.25) = 52.5`
- **Cap-fill eat** at dawn: if agent is home, it tops up to 100 — restoring exactly what was lost. One meal/agent/day suffices.
- **Per-colony stock burn when all 3 agents eat at dawn:** `3 × EAT_COST = 18 / day`.
- **Stock pile of 18 = 1 day of full camp reliance.** By dawn of day 2, stock is near zero unless replenished by harvest.
- **Wild food buffer (day 1 only):** ~180 units / 5 per forage = 36 wild forages total across all colonies. At ~12 wild forages/day (one per agent), wild food fully depletes by end of day 3. During those days, agents who wild-forage during day reach dawn already full → skip `ate_from_cache` → stock burn is *lower* than the 18/day ceiling.
- **First harvest timing:** plant on day 1, 60 daylight ticks to mature = mid-day 3 (daylight phase of day 3). One crop = `HARVEST_YIELD = 9` stock = 1.5 days of dawn meals.
- **Break-even after wild depletes:** each colony needs ≥2 crops maturing per 3 days per 3 agents. With `MAX_FIELDS = 4`, this is achievable but requires early planting discipline.

**Resulting dynamic:**
- Day 1-2: agents coast on wild food + stockpile. Smart colonies plant during spare day ticks.
- Day 3: wild dries up. Stock stretches to 1-1.5 days depending on how much wild they ate earlier.
- Day 3-4: first harvests land. Colonies that planted 2+ fields survive. Colonies with 0-1 fields starve visibly.

Demo-friendly — the first colony collapse is likely visible around tick 360-420 (≈day 3-3.5), inside the 5-minute pitch window.

## Test plan

TDD per CLAUDE.md golden rule. Each mechanism: failing reproducer first, impl to green.

### Engine (pure, fast)

- `test_phase_for_and_day_for` — values at ticks 0, 29, 30, 89, 90, 119, 120, 240
- `test_world_tick_growth_only_during_day` — 30 ticks of `world.tick('day')` increments; 30 ticks of `world.tick('night')` does not
- `test_crop_matures_at_exact_threshold` — on tick 60, state flips to `'mature'`, `resource_amount == HARVEST_YIELD`, `crop_matured` event emitted exactly once
- `test_decide_action_day_phase_harvest_wins_over_plant` — on mature tile returns `'harvest'`; on empty tile returns `'plant'` (when room); on growing tile returns neither (falls through)
- `test_decide_action_hunger_critical_overrides_day_productive` — hungry agent on empty wild tile returns `'forage'`, not `'plant'`
- `test_decide_action_respects_max_fields_per_colony` — at `growing_count == MAX_FIELDS`, plant path closes
- `test_dusk_step_toward_camp` — agent 5 tiles from camp, 5 dusk ticks → on camp
- `test_night_halves_hunger_decay` — Δhunger over 30 night ticks = 0.5× Δhunger over 30 day ticks
- `test_dawn_eat_requires_camp_and_stock` — off-camp: no event; on-camp + stock < EAT_COST: no event; on-camp + stock >= EAT_COST + hunger < NEED_MAX: `ate_from_cache` emitted with correct `amount`
- `test_dawn_eat_once_per_agent_per_dawn` — agent on camp eats at tick 0, but subsequent dawn ticks (1..29) emit no further `ate_from_cache` for that agent even though stock > 0
- `test_dawn_eat_skipped_when_already_full` — agent with `hunger == NEED_MAX` on camp at dawn emits no `ate_from_cache`, stock unchanged
- `test_stranded_agent_skips_dawn_eat` — agent not at camp on dawn tick 0 does not emit `ate_from_cache`

### Service (Postgres)

- `test_create_simulation_spawns_4_colonies_at_corners` — exact `camp_x, camp_y` match expected
- `test_agents_distributed_across_colonies` — each colony has `agents_per_colony` agents
- `test_harvested_event_credits_colony_and_resets_tile` — after a `harvested` event, tile is `none`/`resource_amount=0`, colony food_stock += yield
- `test_ate_from_cache_event_debits_colony` — food_stock decrements by `amount` from event
- `test_growing_count_rollup_matches_tile_state` — after N plants, colony.growing_count == N
- `test_migration_wipes_agents_and_tiles` — running migration on pre-existing DB leaves zero rows in both tables (dev-only wipe)

### Route

- `test_world_state_includes_colonies_array` — 4 entries with expected shape
- `test_world_state_includes_sim_day_and_phase` — derived, not persisted
- `test_world_state_phase_changes_across_30_ticks` — step 30 ticks, phase transitions to next

### Integration (demo-critical)

- `test_plant_grow_harvest_round_trip` — seed sim, force-step 1 agent to empty tile, step enough ticks to plant, grow, harvest:
  - assert `planted` event emitted, tile state `growing`
  - after 60 day-phase ticks, `crop_matured` event emitted at that exact `tile_x, tile_y`
  - agent returns to that tile and emits `harvested` with matching coords
  - colony.food_stock increased by exactly `HARVEST_YIELD`
- `test_300_tick_arc_has_multi_colony_harvest` — seed sim, step 300 ticks, assert:
  - `planted.colony_id` was emitted by ≥2 distinct colonies
  - `crop_matured` coords match prior `planted` coords (same tile_x, tile_y)
  - ≥2 colonies have `food_stock > INITIAL_FOOD_STOCK - 10` (i.e. they successfully replenished from harvests, not just drained)

These tests fail the demo if green is faked — the lineage assertion (planted → matured at same coord) can't be cheated by a seed-time mature tile.

### Manual balance calibration

Run `docker compose up` + create sim + step 600 ticks (5 days) at speed=1. Observe via UI:
- At least 2 of 4 colonies alive at day 5 ✓
- At least 1 `planted → crop_matured → harvested` lineage visible in event log ✓
- `food_stock` curves cross over (some rise, some fall) ✓

Budget 2-3 tuning passes (half-day). Tune `INITIAL_FOOD_STOCK`, `HARVEST_YIELD`, `WILD_RESOURCE_MAX` if all 4 survive (too easy) or all 4 die (too hard).

## Open risks

1. **RNG unlucky start** — mitigated: seed-time density floor (§service layer changes).
2. **Dusk pathing too slow on larger maps** — mitigated: map shrunk 30×30 → 20×20 per scope review. Max corner-to-opposite-camp ≈ 26 tiles on old map; on 20×20 with camps inset 3, max distance from any tile to own camp ≤ 13 — well within 30 dusk ticks.
3. **Balance iteration overrun** — fallback: accept 2-of-4 alive as DoD; do not chase "all 4 survive." Numbers in the Balance section are the starting point, not locked.
4. **Frontend time budget** — fallback order if short on time: (a) drop crop sprites (show tile color shift only), (b) drop tint overlay (ClockWidget alone still tells the story), (c) drop colony-colored agents (all one color, camp squares carry identity).
5. **Demo pacing dead zone** — first 90s of fresh sim looks like "ants wander." Mitigation (optional): demo-mode sim-create that starts at `current_tick = 240` (day 2 dawn) with one colony's `food_stock` pre-set to 5 — drops interviewer into the interesting arc immediately. Single new query parameter on `/sim/create`, trivial to add.
6. **Alembic migration on stale Docker volume** — mitigation: run clean-slate `compose down -v && up` today (Wednesday), not Friday morning.
7. **Interview deep-cut questions to rehearse:**
   - "Two agents harvest the same mature tile on the same tick." Answer: agent iteration order is deterministic by agent.id (existing `Simulation.step`); first agent harvests, second sees `crop_state='none'` and falls through to other branches. No locking needed because the engine is single-threaded.
   - "How does sim reload preserve phase?" Answer: `current_tick` is persisted on `SimulationState`; `phase` is a pure function of it — derivation survives any restart.

## Definition of done

- All engine + service + route tests green
- Integration tests (`test_plant_grow_harvest_round_trip`, `test_300_tick_arc_has_multi_colony_harvest`) green — the lineage assertion gates the demo
- Manual 5-day run: ≥2 of 4 colonies alive at day 5, harvest event lineage visible
- ClockWidget + phase tint rendering at 2 ticks/s
- Agents + camps visibly colored per colony
- HUD shows per-colony food_stock + growing_count
- One commit per subsystem (data model+migration, engine cycle+actions, service wiring, frontend) for a clean interview walkthrough
