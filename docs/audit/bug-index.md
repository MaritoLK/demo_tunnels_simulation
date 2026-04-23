# Bug & Step Repro Index

Standalone reproducers from the Tunnels foundation/cultivation hardening
work. Each script isolates one issue with pre-fix vs post-fix behavior.
They are **not** part of the pytest suite — keeping them out of the regular
run preserves test speed. Run manually when you want to demonstrate or
re-verify a specific issue.

## How to run

From inside the `flask` container, with the stack up:

```bash
docker compose run --rm flask python -m docs.audit.bug1_water_trap
```

`step6_routes.py` and `step7_reload.py` need a live stack (`docker compose
up -d`) before invocation.

## Bug repros

| File | Class | Issue | Fix asserts |
|------|-------|-------|-------------|
| `bug1_water_trap.py` | correctness | `step_toward` got stuck at water with no detour fallback | agent reaches food via explore fallback |
| `bug2_rng_leak.py` | correctness | `forage→explore` fallback dropped `rng`, leaked to global `random` | runs are deterministic regardless of global random pollution |
| `bug3_dead_state_assign.py` | py-quality | `tick_agent` set `agent.state='resting'` then immediately overwrote it | removing the dead assignment changes nothing observable |
| `bug4_socialise_order.py` | correctness | `socialise` mutated both agents; iteration order shifted clamped values at `NEED_MAX` | A's final social is order-independent |
| `bug5_n_flush.py` | perf | per-agent `flush()` in `create_simulation` caused N round-trips | bulk insert collapses to 1 INSERT |
| `bug6_no_rollback.py` | correctness | `create_simulation` lacked `try/except`; failure left session in `PendingRollbackError` | failure path rolls back cleanly |
| `bug7_zero_walkable.py` | defensive | seeded `World.generate` could roll zero walkable tiles → spawn raises | generator guarantees ≥1 walkable tile |
| `bug8_rng_coupling.py` | defensive | shared rng for spawn + tick — adding a spawn shifted every tick roll | sub-seeded `rng_spawn` / `rng_tick` keep tick stream independent |
| `bug9_own_tile_food.py` | correctness | `adjacent_food_tile` ignored agent's own tile — agent on food starves | agent on food can eat it |
| `bug10_colocated_socialise.py` | correctness | `adjacent_agent` required Manhattan distance == 1, ignoring co-located agents | co-located agents can socialise |
| `bug11_spawn_collision.py` | correctness | `spawn_agent` picked uniformly with no occupancy check | spawn picks unoccupied tile when one exists |
| `bug12_rng_optional.py` | py-quality | every action defaulted `rng=None`; `explore` fell back to global `random` | actions reject missing `rng` at API boundary |
| `bug13_pre_decay_death.py` | correctness | `tick_agent` decayed needs before checking `health <= 0` | already-zero agent skips decay |

## Step verifiers

| File | Purpose |
|------|---------|
| `step6_routes.py` | Live HTTP smoke against every route; happy + representative error paths |
| `step7_reload.py` | Cold-start reload preserves sim state + RNG trajectory bit-for-bit |

## Status

All bugs documented here are fixed in the engine. Scripts moved from
`backend/audit/` to `docs/audit/` on 2026-04-23 to make the boundary
between production code and post-mortem documentation explicit.

If you add a new repro: name it `bugN_<slug>.py`, follow the existing
docstring format (problem statement → pre-fix vs post-fix behavior →
test setup), and add a row to the table above.
