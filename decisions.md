# Tunnels — Cleanup Decisions Log

**Branch:** `archive/python-foundation`
**Started:** 2026-04-23
**Re-demo target:** Tuesday 2026-04-28 (≈5 days runway)
**Baseline verified this session:** 227 backend tests + 37 frontend tests = **264 green** (pytest 5.47s, vitest 33s)
**Audit method:** 3 parallel read-only Explore agents (backend / frontend / infra+test). Zero code changes in Phase 1.

> Living document. Each item moves: `proposed` → `approved` → `done` / `rejected` / `deferred`.
> Per `CLAUDE.md` golden rule: any finding labelled "candidate" requires reproduction before being treated as a confirmed bug.

---

## Tier scheme

| Tier | When | Risk | What |
|------|------|------|------|
| **T0** | Pre-demo | None | Docs, naming, file hygiene, deletions of clearly stale files |
| **T1** | Pre-demo | Low | Small dedup, named constants, drop-in helpers, comments |
| **T2** | Post-demo | Medium | Structural refactors (hook extraction, method splitting, BFS unify) |
| **T3** | Deferred | Depends | Legacy-path retirement, dual-track collapses, gated on test migration |

---

## Open questions — need your call before Phase 2 starts

These block / shape the cleanup. Please answer inline (edit this file) or in chat.

1. **Branch name `archive/python-foundation`** — semantically reads "archived" but it is the active working branch. Options:
   - (a) Rename → `main` (if this is the production branch going to demo)
   - (b) Rename → `feat/foundation` (if foundation is still a feature branch off main)
   - (c) Keep as-is (and note rationale in `CLAUDE.md`)
   - **Need decision.**
2. **Untracked plan `docs/superpowers/plans/2026-04-15-day-night-cultivation.md`** (3,483 lines, day/night feature plan). Day/night already shipped per memory. Options: commit to repo (history record) / move to a `docs/superpowers/plans/archive/` folder / delete. Recommend **commit** as historical record.
3. **Deleted file `TUNNELS_PROJECT_BRIEF.md`** still uncommitted. Recommend **commit the deletion** — content superseded by `CLAUDE.md` + design specs. Confirm?
4. **`backend/audit/` scratchpad** (15 bug-repro scripts ~40 KB). Useful for interview discussion, but not test code. Options:
   - (a) Keep in-repo as-is
   - (b) Move to `docs/audit/` and add a one-page `bug-index.md` mapping repro → fix commit
   - (c) Delete after capturing summaries in `STUDY_NOTES.md`
   - Recommend **(b)** — preserves interview value without polluting backend/.
5. **Foundation in-flight files** (Tasks 3+ of `2026-04-17-tunnels-foundation.md` not yet built — `engine/world_state.py`, `engine/event_bus.py`, etc.). User said "cleaning > dev now". Confirm: pause foundation Task 3 dispatch until cleanup done?
6. **Legacy compat paths** (`_legacy_decide_action`, `_legacy_tick_agent` in `engine/agent.py`). Backend agent flagged these as dead-code-pending-test-migration. Want to retire them pre-demo (risky — many tests still call legacy form) or defer to post-demo?
7. **Granularity of Phase 2 commits** — one big "cleanup" commit per tier, or one commit per item (more reviewable)? Recommend **one commit per finding** (easier rollback).

---

## Tier 0 — Pre-demo, safe (do first)

| # | Finding | File:line | Action | Status |
|---|---------|-----------|--------|--------|
| T0.1 | README claims backend on `localhost:8000` but actual is `:5000` direct, `:80` via nginx | `README.md:19` | Fix port to `:5000` (or `:80` if nginx-fronted is preferred) | **done** (4ceda75) |
| T0.2 | `CLAUDE.md` interview date stale: says `2026-04-17`, actual re-demo is `2026-04-28` | `CLAUDE.md:30` | Update date + clarify "re-demo" vs original demo | **done** (9d25363) |
| T0.3 | `frontend/src/test/setup.js` is a stale duplicate of `setup.ts`; `vite.config.ts` only loads `setup.ts` | `frontend/src/test/setup.js` | Delete file (-7 LOC) | **done** (a36680c) |
| T0.4 | `frontend/src/test/smoke.test.ts` is a placeholder (`expect(1+1).toBe(2)`) — zero signal | `frontend/src/test/smoke.test.ts` | Delete file (-8 LOC) | **done** (35ecfb1) |
| T0.5a | Deleted `TUNNELS_PROJECT_BRIEF.md` uncommitted | repo root | Commit deletion | **done** (f282be9) |
| T0.5b | Untracked `2026-04-15-day-night-cultivation.md` plan | `docs/superpowers/plans/` | Commit as historical record | **done** (bb79a8b) |
| T0.6 | Branch `archive/python-foundation` semantically misleading | git refs | Rename to `master` (local; push deferred) | **done** (local) |
| T0.7 | `backend/audit/` is post-mortem documentation living in source tree | `backend/audit/**` | Move to `docs/audit/`, add `bug-index.md`, update `.gitignore` | **done** (26a2bdd) |

**T0 LOC delta (actual):** −534 source/text, +3,759 docs. Frontend tests: 37→36 (smoke deletion). Backend tests: 227→227.

---

## Tier 1 — Pre-demo, low risk

### Backend

| # | Finding | File:line | Action | Status |
|---|---------|-----------|--------|--------|
| T1.B1 | `world.py:71` redundant `self.tiles = []` overwritten by `generate()` line 94 | `backend/app/engine/world.py:71` | Delete line | **done** (5fb5d45) |
| T1.B2 | Inconsistent local imports: `from . import config` inline in `actions.py:385, 511` (and `world.py:162`) | `backend/app/engine/actions.py`, `world.py` | Hoist to module top | **done** (e7b9d96) |
| T1.B3 | `rest()` and `rest_outdoors()` near-identical | `backend/app/engine/actions.py:259-292` | Collapse via helper or boolean flag | **rejected** — bodies differ in 4 dimensions (energy multiplier, heal branch, event type, description). Helper + 2 wrappers nets ≈0 LOC and adds indirection. Per CLAUDE.md "no premature abstraction." |
| T1.B4 | `tile_to_row_mapping()` only used by `audit/` scratchpad scripts | `backend/app/services/mappers.py:68-78` | Delete + inline pre-fix shape into bug5/bug6 scripts | **done** (d449ee5) |
| T1.B5 | Add docstrings to `engine/cycle.py`, `engine/config.py`, `engine/needs.py` constants | various | +15 doc lines | **rejected** — constants are well-named; module docstrings already cite the spec for derivation; per CLAUDE.md "default to no comments" the inline rationale would be filler. |
| T1.B7 | `simulation_service.py` dirty-tile + dirty-colony discovery share a pattern | `simulation_service.py:237-251` | Extract `_event_keys_by_type` helper | **rejected** — projection differs (tuple vs scalar) + filter sets differ; helper would require lambda + frozenset per call, growing each callsite. Two 4-line set-comps stay clearer. Per CLAUDE.md "three similar lines is better than premature abstraction." |
| T1.I2 | Migration `env.py:21` uses deprecated `get_engine()` | `backend/migrations/env.py:21` | Use `db.engine` directly (pinned Flask-SQLAlchemy 3.1.1 supports it) | **done** (5e1e3c7) |

### Frontend

| # | Finding | File:line | Action | Status |
|---|---------|-----------|--------|--------|
| T1.F1 | Duplicated scalar constants across components | various | Create `frontend/src/constants.ts` | **rejected** — only `CARRY_MAX` actually duplicates (2 callsites: AgentPanel, Canvas2DRenderer); `CROP_MATURE_TICKS` and `TICKS_PER_PHASE` are single-use. Author's "wire boundary" comment justifies the local-mirror pattern. Centralizing 1 scalar with explicit author rationale = preemptive (YAGNI). |
| T1.F3 | `WorldCanvas.tsx:276` `useViewStore.getState()` inside wheel handler | `WorldCanvas.tsx:276` | Use closure `zoom` value | **rejected** — `zoom` is NOT in the useEffect deps array (line 303). Closure capture would be STALE on zoom change. `getState()` is the correct intentional fix; audit had the bug direction backward. |
| T1.F4 | `STATE_LABEL` mirrors backend state strings without typed bridge | `Canvas2DRenderer.ts:74-85` | Add doc comment | **rejected** — comment alone doesn't fix the coupling; the real fix is exposing states in API envelope (T3 candidate). Filler comment would degrade rather than clarify. |
| T1.F5 | Magic XOR constants `73856093`, `19349663` in spatial hash | `Canvas2DRenderer.ts:280` | Hoist as named constants | **rejected** — these are the classic Teschner et al. spatial-hash multipliers; a reader knowledgeable about hashing recognises them inline. Naming with a 1-line comment adds 4 LOC for marginal recognition gain. |
| T1.F6 | `App.tsx:67-71` five `<LabeledNumber>` calls | `App.tsx:67-71` | Loop over param descriptors | **rejected** — 5 hand-named form fields is enumeration, not duplication. Each line answers "what fields exist?" directly. Loop hides intent for marginal LOC save. |
| T1.F7 | `App.tsx` `NUMBER_FORMATTER` wrapper used at one site | `App.tsx:250-254` | Inline `toLocaleString` | **done** (d4d128c) |

### Infra

| # | Finding | File:line | Action | Status |
|---|---------|-----------|--------|--------|
| T1.I1 | CI duplicates `npm ci` in two frontend jobs | `.github/workflows/ci.yml` | Factor or accept | **deferred** — current overhead ~30s, not a blocker pre-demo. |

**T1 actual LOC delta:** ≈ −25 LOC source. 5 accepted, 8 rejected per CLAUDE.md "no premature abstraction" / "no filler comments" guidance.

---

## Tier 2 — Post-demo, medium risk

### Backend

| # | Finding | Files | Proposed action | Why deferred |
|---|---------|-------|-----------------|--------------|
| T2.B1 | `engine/actions.py` BFS duplication: `_first_step_bfs` (lines 50-89) + `_bfs_first_reachable` (lines 92-131) share structure | `backend/app/engine/actions.py:50-131` | Extract `_bfs_walk(agent, world, *, predicate, max_depth)` yielding `(first_step, depth, tile)`; both callers reshape (-25 LOC) | Touches pathfinding hot path — tests must catch any subtle off-by-one. Pre-demo risk too high. |
| T2.B2 | `decide_action()` 103 LOC, 5 levels of nesting | `backend/app/engine/agent.py:57-160` | Decision-table or `@singledispatch` on `(phase, rogue)`. **Backend audit explicitly recommended NOT touching pre-demo** | Logic is subtle, regressions likely. |
| T2.B3 | `simulation_service.create_simulation()` 79 LOC, 5 nesting levels | `backend/app/services/simulation_service.py:131-209` | Factor into `_delete_sim_rows()`, `_create_colonies_and_agents()` helpers | Touches new-sim boot path — demo opens a new sim. |
| T2.B4 | `simulation.step()` colony-aware vs legacy branches duplicate event emission | `backend/app/engine/simulation.py:94-127` | Strategy pattern + extracted event-emit helper (-10 LOC) | Wait until legacy branch retired (T3). |
| T2.B5 | `tick_loop._consecutive_failures` global state | `backend/app/services/tick_loop.py:50,72,83,97` | Wrap in `class TickLoop` instance state (+20 LOC but cleaner) | Background loop — single-worker assumption documented; refactor cosmetic. |
| T2.B6 | `routes/simulation.py:79-142` `replace_simulation()` dense validation | `backend/app/routes/simulation.py:79-142` | Extract `_validate_create_simulation_request(body)` helper (-20 LOC) | Touches new-sim endpoint hit during demo. |

### Frontend

| # | Finding | Files | Proposed action | Why deferred |
|---|---------|-------|-----------------|--------------|
| T2.F1 | `WorldCanvas.tsx` 366 LOC, mixes 4 concerns (data fetch, camera, pointer, renderer lifecycle) | `frontend/src/components/WorldCanvas.tsx` | Extract `useCanvasRenderer()`, `usePointerInteraction()`, `useAutoFit()`, `useFrameSnapshot()` hooks. Net component shrinks to ~100 LOC | High surface area for regressions in canvas interaction (drag/zoom/click — demo-critical). |
| T2.F2 | `Canvas2DRenderer.ts:168-649` `drawFrame()` is 482 LOC orchestrator | `frontend/src/render/Canvas2DRenderer.ts:168-649` | Extract `_drawTerrainPass`, `_drawCampMarkers`, `_drawCropOverlay`, `_drawTileSelection`, `_drawAgents` private methods. Logic stays identical, structure flattens | Same — render path is the demo's first impression. Move post-demo. |
| T2.F3 | Hardcoded color mappings live in 3 files (`AgentPanel`, `Canvas2DRenderer`, `ClockWidget`) | multiple | Extract `frontend/src/colorScheme.ts` (+20 / -10 LOC) | Visual regression risk during pre-demo polish. |
| T2.F4 | Inline JSX styles for badges (rogue/loner/crop) | `AgentPanel.tsx:53-67`, `TilePanel.tsx:56-58` | Extract to CSS classes in `styles.css` (+15 / -16 LOC) | Same as F3 — visual polish window is post-demo. |
| T2.F5 | `Canvas2DRenderer:144-150` fire-and-forget sprite load — safe today but cleaner with disposed flag | `frontend/src/render/Canvas2DRenderer.ts:144-150` | Add `private disposed = false` + check in load callback (+3 LOC) | Cosmetic robustness — current code safe per audit. |

**T2 LOC delta:** ≈ neutral (refactor, not delete). Clarity win significant.

---

## Tier 3 — Deferred (gated)

| # | Finding | Gate | Action |
|---|---------|------|--------|
| T3.B1 | Retire `_legacy_decide_action` + `_legacy_tick_agent` in `engine/agent.py` | All legacy callers migrated | See **Round D fork below** — user-approved scope but two paths (α / β) exist. |
| T3.B2 | `getattr(agent, 'rogue', False)` defensiveness | Bundled with T3.B1 | Replace with direct `agent.rogue` (-2 LOC each site). |
| T3.B3 | Loner-decay re-application after rogue flip (semantic question) | Decision: is "rogue once = always-rogue" intentional? | Add docstring documenting one-way state OR add re-entry guard. **Candidate — needs clarification, not yet a bug.** |
| T3.B4 | `terrain` silent fallback to move cost 1 in `step_toward()`/`forage()`/`explore()` | Decision: fail-loud on missing terrain key, or keep permissive? | Add `assert` or restructure `TERRAIN_MOVE_COST` access. **Candidate — needs design call.** |
| T3.F1 | Refactor `useState` cluster in `App.tsx:28-33` into `useReducer` or `useSimParams()` | Foundation routing lands (App.tsx will be replaced) | Skip — likely obsoleted by router migration. |
| T3.F2 | EventLog key stability under filter/reorder | Reproduce: toggle "selected only" + watch DevTools | **Candidate — needs repro before fix.** |

---

## Round D fork — legacy retirement scope

User green-lit "remove any legacy thing" (2026-04-23). Survey discovered the scope is wider than the audit framed:

**Truly-legacy (uncontested removal targets):**
- `_legacy_decide_action` (engine/agent.py:163-177) — 5-step priority ladder, superseded by 9-step phase-aware ladder
- `_legacy_tick_agent` (engine/agent.py:282-297) — pre-cultivation tick driver
- Gates in `decide_action` (lines 83-88) and `tick_agent` (lines 235-236) routing to those legacy paths
- `getattr(agent, 'rogue', False)` / `getattr(agent, 'cargo', 0.0)` / `getattr(agent, 'loner', False)` defenses (slot-enforced now)

**Wider blast radius (less clear):**
- `Simulation.step()` legacy branch (lines 99/111-122) — calls `tick_agent` with no `colonies_by_id`/`phase`
- `new_simulation(agent_count=N)` convenience overload — used by ~20 test files
- `create_simulation(agent_count=N)` convenience overload — used by ~10 test/integration files
- 8 audit scripts call legacy `tick_agent` directly
- test_agent.py calls legacy `decide_action(a)` 11× and legacy `tick_agent` 5×

### Two end-states

**(α) Minimal — delete the named "_legacy_" code only.**
- Migrate test_agent.py 16 callsites to phase-aware form.
- Migrate 8 audit-script `tick_agent` callsites.
- Delete `_legacy_decide_action`, `_legacy_tick_agent`, the gates, `getattr` defenses.
- Synthesize a default `EngineColony` inside `Simulation.__init__` when `colonies` is empty, so `Simulation.step()` always runs the colony-aware path → preserves the `agent_count=N` convenience overload for the ~30 callers without forcing them to construct colony objects.
- LOC: ≈ −80 source, +12 synthesis logic.
- Risk: low. Subtle behavior shift: agents at (0,0) in legacy-shaped sims now register as `at_camp` (default colony's camp is (0,0)) — a couple of tests may need to relocate their agents away from (0,0), but the engine path they exercise is the canonical one.

**(β) Full — drop the convenience overloads too.**
- Same as α but additionally: remove `agent_count=N` from `new_simulation` and `create_simulation`. Force every caller to construct `EngineColony` objects explicitly (`agents_per_colony=N`).
- Touches ~30 test files, requires a shared `_default_colony()` test helper.
- LOC: ≈ −80 source, +200 test boilerplate.
- Risk: medium-high. Many small test edits in a tight window before re-demo. Anything that mis-migrates becomes a silent test rewrite.

**Recommendation: α.** Same dead-code removal, less churn, no test-behavior surprises beyond the at-camp shift (fixed by repositioning agents). β is a "cleanup of the cleanup" that's better suited to post-demo.

**Awaiting user pick** before Round D execution.

---

## Cross-cutting patterns

### CC.1 — Dual-track legacy compatibility (backend)
- **Where:** `engine/agent.py` (decide_action, tick_agent), `engine/simulation.py` (step), `services/simulation_service.py` (create_simulation), `routes/simulation.py` (PUT /simulation).
- **Why it exists:** Pre-phase / pre-colony APIs preserved during cultivation rollout (T10-T12 in day/night plan).
- **Status:** All 227 tests green via legacy paths.
- **Proposed direction:** Tier 3 retirement after a dedicated test-migration commit. Document in `STUDY_NOTES.md` first.

### CC.2 — Magic constants (backend + frontend)
- **Where:** `engine/{config,needs,actions,world}.py` constants without inline rationale; same scalars copy-pasted into 2-3 frontend files.
- **Direction:** T1 — add one-line "why" comments backend-side; create `frontend/src/constants.ts` for engine-tied scalars.

### CC.3 — Color/style hardcoding (frontend)
- **Where:** Badge styles inline, color hex strings in `Canvas2DRenderer`, `AgentPanel`, `ClockWidget`.
- **Direction:** T2 — single `colorScheme.ts` module post-demo.

### CC.4 — Frontend↔backend semantic coupling without typed bridge
- **Where:** `Canvas2DRenderer.STATE_LABEL` mirrors `actions.STATE_*`; constants like `CARRY_MAX`, `CROP_MATURE_TICKS` duplicated.
- **Direction:** T1 (frontend constants file). T3 (long-term: ship constants in API envelope or generate types from backend).

---

## Foundation in-flight (informational — DO NOT TOUCH)

Per `docs/superpowers/plans/2026-04-17-tunnels-foundation.md`, Tasks 1 & 2 shipped (e4d7958, 2733d1d). Tasks 3+ pending.

**Files to leave alone during cleanup:**
- `backend/app/models/{game_state_row,npc,relationship,event_log,policy,save_meta}.py`
- `backend/app/services/game_mappers.py`
- `backend/migrations/versions/f7e8d9a0b1c2_game_foundation.py`

These are intentionally minimal placeholders. Backend audit confirmed they're consistent with existing patterns (slots, defaults, FK constraints) and ready for Task 3+ integration.

**No cleanup actions proposed against these files.** If anything touches them during Phase 2, that is a regression and should be reverted.

---

## Test-suite observations (flag-only, no Phase 2 actions)

- **Backend:** Could extract a fixture for repeated agent init (`name, x, y, colony_id`) and an `assert_event(type, data)` helper. Defer — fixture sprawl risk during demo window.
- **Frontend:** Component tests (AgentPanel, ClockWidget, ColonyPanel) are minimal smoke tests — acceptable for current scope. `setup.js` and `smoke.test.ts` covered in T0.
- **Coverage:** Heavy on engine + utilities; lighter on integration. `test_cultivation_arc.py` is the only integration test and it's solid.

---

## Phase 2 plan (gated on your sign-off)

Once you answer the open questions and approve a tier:

1. **Apply T0** in a single commit per file (5-7 commits). Re-run baseline after each. Stop on any regression.
2. **Apply T1** per finding, one commit each. Re-run baseline after each.
3. **Stop here pre-demo.** Tag the cleanup state (e.g., `pre-demo-clean-2026-04-26`).
4. **T2 + T3** post-demo, in a separate branch.

Each Phase 2 commit will:
- Cite this file (e.g., "Refs decisions.md T1.F1") in commit message.
- Update the corresponding row's `status` from `proposed` to `done`.

**Verification gate per commit (golden rule):**
- Backend touched? Re-run `docker compose run --rm flask pytest -q`.
- Frontend touched? Re-run `npm test` + `npx tsc --noEmit`.
- Pasted output (pass count) into the commit description before claiming done.

---

## Phase 1 audit summary (raw counts)

| Area | Files audited | Issues found | Top deferred risk |
|------|---------------|--------------|-------------------|
| Backend | 28 source + 7 migrations + 15 audit scripts | 23 (Dead 3, Dup 5, Cmplx 7, Clean 4, Simpl 3, Risk 1) | Terrain cost silent fallback (candidate) |
| Frontend | 27 source + 8 test = 35 files | 27 (Dead 5, Dup 6, Cmplx 3, Clean 8, Idiom 2, Perf 1, Risk 2) | EventLog key stability (candidate) |
| Infra+Test | 6 subsystems | 11 (3 medium, 8 low) | Branch naming mismatch |

**Audit reports retained in conversation transcript.** This file is the consolidated, actionable layer.

---

## Changelog

- **2026-04-23 12:10** — Phase 1 audit complete. Baseline 264 green confirmed. Decisions doc seeded. Awaiting user sign-off on open questions before Phase 2.
- **2026-04-23 12:55** — Round A (T0) complete. 8 commits (4ceda75 → 30f418a). Branch renamed `archive/python-foundation` → `master` (local). Baseline re-verified: 227 backend + 36 frontend = 263 green (frontend down 1 from smoke.test.ts deletion, expected). Tag: `cleanup-round-a`.
- **2026-04-23 13:10** — Round B (backend T1) executed: 4 accepts (T1.B1, T1.I2, T1.B2, T1.B4), 3 rejects (T1.B3, T1.B5, T1.B7). Commits 5fb5d45, 5e1e3c7, e7b9d96, d449ee5. Pytest after each: 227 green throughout. Deprecation warning in test output eliminated.
- **2026-04-23 13:05** — Round C (frontend T1) executed: 1 accept (T1.F7), 5 rejects (T1.F1, T1.F3, T1.F4, T1.F5, T1.F6). Commit d4d128c. vitest+tsc green: 36 tests, 0 type errors.
- **2026-04-23 13:25** — Round D scope discovery surfaced a wider blast radius than the audit framed. Two end-states drafted (α minimal, β full). Awaiting user pick before any Round D code change.
