# Tunnels — Vision Design

**Version:** 1.0
**Date:** 2026-04-17
**Status:** Approved for MVP implementation
**Supersedes:** 2026-04-15 day/night cultivation spec (colony sim retained as tactical fallback substrate)

This is a compass, not a contract. It locks the shape of the game and the non-negotiable boundaries; implementation details are deferred to sub-project plans.

---

## §1 Premise and core loop

### Premise

A dynastic survival-civ hybrid. The player controls a hero across the founding era of a new kingdom. The hero travels an overworld of hand-authored nodes, fights RPG combat, builds a capital, raises a council, makes alignment choices on multiple axes (primary named axis: **dictator ↔ benefactor**; additional axes are Future-Us) that reshape the world, and leaves a legacy.

**MVP scope is one generation.** Gen 2 / heir handoff is specified in the Future-Us appendix, not shipped. See Non-Negotiable Boundary #8.

### Reference points

- **Volcano Princess** — time-management rhythm, scheduled weeks, life-sim substrate
- **Crusader Kings III** — council competence as core fantasy, attributed consequences
- **Mount & Blade** — overworld graph + local map architecture
- Tech baseline: medieval/early-modern. Magic is niche (Touched flag persisted on ~10–15% of NPCs, no mechanics in MVP).

### Core loop

One session = a handful of scheduled weeks on the life-sim + one tactical excursion to a local node. Per session the player:

1. Allocates weekly schedule slots (Train / Court / Patrol / Rest / Research)
2. Reviews alerts and issues policy changes
3. Picks an overworld destination, pays the day-cost, and enters a local node
4. Plays tactical gameplay (combat, exploration, dialogue, recruitment scenes)
5. Returns to court; deferred events drain in priority order; time advances
6. Every 12 weeks (first digest at week 4): a council digest summarises attributed outcomes

Win condition: **found and secure the capital** (~20–30 in-game years).
Loss conditions: hero dies of natural causes before win, or council loyalty floor is breached (coup).

### Agency and depth tiers

| Layer | Depth | Player input |
|-------|-------|--------------|
| Tactical (local nodes, combat, scenes) | **Deep** | Direct control |
| Life-sim (schedule, court, relationships) | **Medium in MVP** (scaling to Deep-adjacent post-MVP) | Direct control |
| Overworld (graph traversal) | **Thin** | Pick destination; travel is autonomous |
| Strategic (kingdom, economy, policy) | **Thin** | Policy knobs + alert responses |
| Spouse | **Medium** | Courtship + scheduled court slot |
| Magic | **Niche** | Flag-only in MVP |

The hero is the locus of simulation. The rest of the kingdom is abstracted to numerical state with flavor text.

---

## §2 Architecture and systems

### Four layers, one active at a time

| Layer | Tick rate | Scope | Engine module |
|-------|-----------|-------|---------------|
| Tactical | turn-based (MVP) | Hero's current local node | `engine/tactical.py` (new) |
| Life-sim | daily / weekly slots | Hero's court schedule | `engine/strategic.py` (new, scheduler-coupled) |
| Strategic | weekly tick | Kingdom regions, policies, alerts | `engine/strategic.py` (new) |
| Overworld | event-driven | Node graph traversal | `engine/strategic.py` (new, overworld submodule) |

Only one layer owns player input at a time. All layers mutate world state on their own ticks. The event bus commits per tick (transactional; batched writes, no mid-tick observers). Cross-layer reads use the last-committed snapshot.

### Time cartography (model "b": scheduled-time cost)

The life-sim scheduler is the universal clock.

- **Overworld travel**: costs days, deducted from the life-sim allocator. On exit, strategic ticks a proportional number of weeks.
- **Tactical excursion**: player commits to a duration at entry ("quick scout" 1d, "full expedition" 14d). Cost is legible before commit. Strategic ticks frozen during excursion; deferred events accumulate and fire on return in priority order.
- **Retroactive P0 handling (MVP)**: a P0 event that would have fired mid-excursion still fires on return, timestamped ("8 days ago"). Model (ii) — consequence mutation based on lateness — is Future-Us.

### Alert tiers (event surfacing rules)

Events live on the bus at priorities P0–P3. "Alerts" are the UI surfacing of P0–P2 events; P3 events never alert, they only appear in the digest rollup.

| Tier | Examples | Surfacing |
|------|----------|-----------|
| P0 existential | Succession crisis, capital siege, coup | Hard-return (tactical force-ends, forced travel, checkpoint) — **zero in MVP** |
| P1 strategic | War declared, plague outbreak, spouse death | Pause-and-notify **during life-sim only**; during tactical → silent red HUD pip, queued |
| P2 social | Councilor drama, heir milestone, betrayal | Deferred; drain on life-sim return in priority order |
| P3 flavor | Village gossip, traveller news, minor trade | No alert. Collapse into digest ("while you were away…") |

**Non-negotiable**: no mid-combat modals, ever. Red HUD pip is ambient-only (no sound sting) to prevent reflexive pauses.

### NPC registry tiering

| Tier | Who | Cap | Memory |
|------|-----|-----|--------|
| T1 | Hero, spouse, council, named rivals (heir + ancestors post-MVP) | ~25 | Full event log + recall |
| T2 | Recurring per-node NPCs (innkeepers, quest-givers, recruits) | ~100 | Ring buffer of last 20 events with hero |
| T3 | Flavor named NPCs | ~500 | 1–2 flags |
| T4 | Generic population | unbounded scalar | None |

**UX constraint**: **meet in scene, not stat block.** Named NPCs must be introduced through a scene (recruitment, event chain, dialogue beat). Never spawn named NPCs directly into stat panels. UI reinforces identity with portrait + name + title + relationship-to-hero tag on every mention.

Named-rivals bucket starts at 3–4 at game start and grows through play as the hero makes enemies and allies.

### Node hydration model

3 hand-authored persistent nodes for MVP (4–5 is Future-Us). Each has a **lightweight state** (always resident, canonical) and is hydrated into a **tactical-scale deep state** only on entry.

**Lightweight state** (per node, stored in save, ~2 KB):

- Node ID, name, biome template
- Faction control, development level (0–5), infrastructure flags (walled / farmed / ruined / tournament-hosting)
- Persistent monument list (player-authored buildings + destroyed landmarks)
- T1/T2 NPCs resident here with `{alive, dead, away}` status
- Economy snapshot: `{prosperity, trade_volume, last_harvest_quality}`
- Outstanding event flags: booleans ("bandit_problem_unresolved", "plague_rumors", "tournament_scheduled")
- Player-authored history log: 2–5 entries, append-only, compressed (~200 bytes total)
- Faction opinion toward hero's dynasty (scalar, separate from faction control)
- Last-visit tick

**Hydrated state** (derived view, discarded on exit):

- Full tile grid, buildings, T3 NPC roster, local quest beats, weather, time-of-day
- Built on entry from lightweight state + node template
- On exit: write back building changes, ruins, monuments, T3 deaths. Discard the rest.

Rule: **lightweight state is canonical.** Saves store only lightweight state. Hydrated state is always reproducible.

### Scene system (new infrastructure)

`tactical/scene_system.py` is the reusable scene runner. It ships with:

- Sequence + branching
- Dialogue UI (portrait + text + choices)
- Stat-reveal helper (a scene beat exposes 1 stat of a target NPC)
- Commit / decline flow

First MVP consumer: `recruit_scene.py` (council recruitment). Future consumers (heir handoff, death, marriage, quarterly digest flavor) reuse the same system.

### Council UX wiring

Each locked UX rule has a concrete backing module.

| Rule | Module | MVP scope |
|------|--------|-----------|
| 1a Legible stats | `ui/CouncilorCard.tsx` | 4 stats visible: Competence / Loyalty / Ambition / Specialty. Numeric + icon. |
| 1b Attributable consequences | `engine/alert_attribution.py` | Every strategic event carries `source_councilor_id` or `source_policy_id`. UI surfaces "Steward Aldric failed the harvest (Competence 2)." |
| 1c Survivable first council | `engine/new_game.py` | Starter generation guarantees ≥1 competent per specialty. Dev-only constant `NEW_GAME_COUNCIL_GENEROSITY = 1.2` — **no difficulty UI in MVP.** |
| 1d Recruitment as scene | `tactical/recruit_scene.py` (via scene_system) | Player meets candidate in a local node, 2–3 dialogue beats reveal 2–3 stats, then commits. |
| 1e Quarterly digest | `engine/council_digest.py` + `ui/DigestModal.tsx` | Fires at week 4 (frontloaded), then every 12 weeks. 5–10 councilor-attributed lines. |

### Event log retention

`event_log` is append-only. Retention differentiated by tier so P3 flavor doesn't dominate:

- **P0–P1**: keep forever (load-bearing for dynasty continuity — see Future-Us)
- **P2**: last 500
- **P3**: last 100, or collapse into digest rollup after 12 weeks

Indexed on `source_id` so future dynasty-scale queries ("places Theo I visited") can derive from the event log without a dedicated travel table.

### Persistence schema (MVP, SQLite)

Single file per save. Tables:

```
world_state     (singleton row; year, tick, active_layer, alignment_axes)
hero            (stats, inventory, wounds, twilight_flag)
npc_registry    (id, tier, name, stats_json, memory_json, status)
relationships   (npc_a, npc_b, type, strength)
nodes           (id, lightweight_state_json)  -- see §2 hydration
event_log       (tick, tier, source_id, payload_json)  -- indexed on source_id
policies        (id, name, effects_json, active_until_tick)
save_meta       (schema_version, playtime, gen_number)
```

Policy effects live in a JSON blob on the `policies` row (no separate modifier table in MVP).

**Save rules**:

- Autosave on every layer transition (life-sim ↔ tactical, tactical ↔ overworld, etc.)
- Manual save allowed only from the life-sim layer
- Tactical excursion is atomic: start-of-excursion autosave is the rewind point on mid-combat quit
- Hard-return events (Future-Us) commit partial tactical state + apply consequence — no save-scum

### Flask route boundary

- `/api/v1/world/state` — **shape unchanged**, tactical-only. Existing 37 frontend tests + nginx cache continue to work.
- `/api/v1/game/state` — new composite endpoint for life-sim / strategic / overworld views.
- `/api/v1/game/*` — new mutation routes for policies, scene advancement, schedule commit, etc.

No silent breaking changes to the existing tactical state contract.

### Frontend layer boundary

- `/tactical` route mounts the existing canvas
- `/court`, `/overworld`, `/council` routes mount React views
- **Route-level switching only.** Canvas and React views never render concurrently.
- Shared state: Zustand store hydrated from `/api/v1/game/state` poll. Transition = unmount + remount. No in-place swap.

### Engine module plan

New files:

- `engine/tactical.py` — tactical-layer sim (RPG combat, scene runner wiring)
- `engine/strategic.py` — strategic tick (regions, policies, alerts, overworld graph traversal, life-sim scheduler)
- `engine/world_state.py` — shared canonical state + event bus
- `engine/alert_attribution.py` — source tagging for strategic events
- `engine/council_digest.py` — periodic digest builder
- `engine/new_game.py` — starter council + world generation
- `tactical/scene_system.py` — reusable scene infra
- `tactical/recruit_scene.py` — first scene instance

Existing `app/engine/simulation.py` (colony sim) is **not renamed** and **not modified** for MVP. It remains available as the tactical layer's deep fallback substrate for outdoor exploration nodes. 213 existing backend tests stay green. A file-header comment documents its role going forward.

No LLM sidecar in MVP. All dialogue is templated with named slots. T1 memory selects variants.

---

## §3 MVP scope and non-goals

### MVP — what ships

**One generation. One hero. One lifespan. One win condition.**

- 1 hero with character creation (stats + alignment seed)
- 1 spouse, chosen mid-game; trait roll (~50%); **unkillable in MVP by game-state rule**
- 3 hand-authored nodes (capital ruin + 2 satellites)
- Overworld graph of ~5 travel edges connecting them
- **Tactical**: combat for 1 party member (hero solo), 3 enemy archetypes, grave-wound on defeat → return to court (no death from tactical). **Grave-wound cost**: persistent stat debuff until cleared by Rest-slot recovery + N weeks forfeited to forced travel home + 1 P2 event fires ("the hero returned broken"). Defeat is not free.
- **Life-sim**: 5 schedule slots:
  - Train — stat progression
  - Court — with sub-target (spouse / councilor / faction rep)
  - Patrol — surface local alerts, minor XP
  - Rest — active wound recovery; when no wound pending, grants a household-relationship tick (spouse or one councilor bond +1) so the slot is a genuine alternative to Train, not a trap option
  - Research — slow unlock track for policies / tech flavor
- **Strategic**: 4 policies (tax / levy / law / trade), weekly tick, alert system, quarterly digest
- **Council**: 5 slots (Steward / Marshal / Spy / Chancellor / Priest), recruitment scene, attribution on alerts
- **10 authored event chains** (not 15): 3 main-plot (capital founding arc), 4 council/spouse chains, 3 flavor
- **Twilight UI** at age 55. Natural death around age 60–65. Telegraphed, not surprise.
- **Two loss beats**: coup epilogue scene, "work unfinished" natural-death epilogue scene (one paragraph + static art each)
- **One victory beat**: capital founded and secured epilogue
- Save/load (SQLite, autosave per transition + 3 manual slots)
- **5–7 achievements** ("Founded the capital", "Served by a 4+ council", "Survived the Year 12 plague", etc.)

No sound. Text + art only.

### MVP success criteria

One external playtester completes a full generation (hero creation → capital secured **or** coup/natural-death loss epilogue) without getting stuck on systems UX, and can articulate the council-competence fantasy in their own words. Shipping the feature list is not shipping the game.

### Non-goals (the important list)

**Dynastic:**

- Gen 2, heir play loop, heir raising / education
- Succession crisis, remarriage
- Ancestor scene recall, dynasty tree view
- Faction opinion toward dynasty beyond a single scalar

**Narrative / content:**

- LLM dialogue, voiced audio, cutscenes
- Localization
- Magic system (Touched flag persists; no mechanics)
- Procedural node generation
- Branching endings beyond the three locked above

**Mechanical:**

- Multi-party tactical combat
- Tactical stealth / social alternatives to combat
- Crafting
- Trade routes as mechanic (trade is one strategic scalar)
- Wildlife / weather simulation
- Real-time strategic tick (model "c" from time cartography)
- Mid-combat alerts of any kind
- Hard-return events (zero in MVP)
- Dynamic faction AI (factions = scripted behavior tables)
- Controller, mobile, multiplayer, mod support
- Difficulty settings (council generosity is a dev constant)
- Spouse death content (mechanics specced, no content ships)

**Infra:**

- LLM sidecar service
- Non-SQLite persistence
- Migration tooling beyond the existing Alembic pattern
- Cloud saves, telemetry
- Authentication on control endpoints — consciously deferred. Secure-by-topology today (loopback + nginx). Trigger to revisit: first time the Flask port is exposed beyond localhost; endpoints become anonymous-writable the moment that changes.

---

## Appendix A — Non-negotiable boundaries

These propagate from §1–§3 and cannot be traded without redesign.

1. **No mid-combat modals, ever.** Tactical flow is sacred.
2. **Tactical excursions are atomic commits.** No mid-combat save-scum.
3. **Lightweight node state is canonical.** Hydrated state is a derived view; saves store only lightweight.
4. **Meet in scene, not stat block.** Named NPCs arrive through scenes. No direct stat-panel spawns.
5. **Council competence is legible and attributable.** Every alert names its source. Every councilor's stats are visible.
6. **Templates canonical; LLM (if added) is a view.** The template system is the contract; no feature is allowed to depend on LLM output.
7. **One active layer owns player input.** All layers mutate world state on their own ticks; input is single-owner.
8. **MVP is one generation, non-interactive epilogue at death.** Gen 2 is Future-Us. Any scope drift toward heir play, succession, or dynasty continuity in MVP is a conscious violation of this boundary.

---

## Appendix B — Future-Us stubs

Each is a one-line promise to revisit. No MVP dependency.

- **Gen 2 / heir play**: authored heir loop, inverse Volcano Princess (play the child you raised).
- **Magic system**: Touched mechanics, enchanted weapons, adventurer niche (10–15% Touched rate playtest).
- **Procedural nodes**: template-based generation for late-game exploration tier.
- **Local LLM dialogue**: optional view over templates, not a replacement.
- **Succession chains**: spouse death, remarriage, succession crisis as P0 events.
- **Multi-party tactical**: recruit companions in scenes, squad combat.
- **Dynamic faction AI**: emergent behavior from policy + opinion state, not scripted.
- **Deeper economy**: trade routes as entities, supply chains, price dynamics.
- **Hard-return events**: siege / coup / heir kidnapped (<5 per full playthrough).
- **Retroactive P0 alerts**: model "ii" — "you were too late" consequence mutation.
- **Cross-generation event_log queries**: "places your grandmother visited", dynasty view.
- **Touched adventurers as tactical recruit pool.**
- **40+ event chain content expansion** (MVP ships 10).
- **Mortality for spouse**: architecture supports it; content ships later. MVP flags spouse unkillable by game-state rule.

---

## Sub-project decomposition

MVP is too large for one implementation plan. It decomposes into:

- **A — Foundation (council competence + scaffolding)**: scene system + recruit scene + alert attribution + digest + starter generation. Also lands prerequisite scaffolding (`world_state.py`, `event_bus.py`, NPC registry + event log + policies models, `/api/v1/game/*` namespace, React Router migration, Zustand store stub). **Implement first** — load-bearing for strategic UX and for every later sub-project.
- **B — Tactical combat**: combat loop, 3 enemy archetypes, grave-wound flow. Depends on `world_state.py` + `tactical.py` scaffolding from A (not the scene system itself).
- **C — Life-sim scheduler**: 5 schedule slots, time accountant, court sub-targets. Parallelizable with B.
- **D — Strategic tick**: regions, policies, alerts, overworld graph. Depends on A (alert attribution).
- **E — Persistence + routing**: SQLite schema, autosave, new Flask routes, Zustand store, route-level frontend switching. Foundational; stub can land early, full form alongside D.
- **F — Content**: 10 event chains, 3 nodes, 5–7 achievements, 3 epilogue scenes. Parallel with systems work.

Each sub-project gets its own spec → plan → implementation cycle. This document is the shared compass they reference.
