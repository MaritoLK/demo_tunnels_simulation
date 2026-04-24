# Netcode Smoothness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the poll-based snap-to-target rendering with a server-push netcode + client interpolation buffer so agents glide smoothly at 60 fps, lifecycle transitions fade instead of popping, and a mid-run world regeneration no longer FK-crashes the tick loop.

**Architecture:** Backend gains (a) a module-level `RLock` that serializes `PUT /simulation` against the tick loop so a regen can't wipe the `agents` table while the loop has pending event rows referencing old agent IDs, (b) `server_time_ms` + `tick_ms` on every snapshot payload so the client can reason about time rather than polling cadence, (c) a new Server-Sent Events endpoint `/api/v1/world/stream` that pushes one snapshot per tick boundary. Frontend subscribes via `EventSource`, maintains a 2-snapshot ring, renders at `serverTime - INTERP_DELAY_MS` (always between two known frames), eases out cubically, widens the snap-guard from `dx²+dy² > 2` to `> 8`, and fades lifecycle appear/disappear over 250 ms. REST `/world/state` poll remains as fallback when EventSource errors.

**Tech Stack:** Python 3.12 / Flask 3 · Werkzeug threaded dev server (already on by default) · SQLAlchemy 2 · React 18 · `@tanstack/react-query` v5 · Canvas 2D · vitest.

**Context:** Brainstorming was done in-conversation with the user (2026-04-24) after their re-demo walkthrough surfaced "teleport, stiff, appear/disappear" symptoms. Reference: `scripts/repro_put_race.py` reproduces the PUT-vs-tick FK violation; `scripts/repro_teleport.py` confirms interpolation math is correct at baseline but linear-lerp + 1 Hz tick feels robotic.

**Re-demo deadline:** 2026-04-28 (Tue) — this plan is demo-blocking work.

---

## Out of scope (explicit)

- WebSocket bidirectional transport (SSE is one-way, sufficient for a passive observer; WS would be post-demo).
- Delta snapshots (send only changed agents). Full snapshot at 1 Hz tick is ~6 KB for 12 agents; bandwidth is not the bottleneck.
- Client-side prediction — there is no local-user action to predict.
- Extrapolation beyond last known snapshot — the interp buffer intentionally lags by `INTERP_DELAY_MS`; if the buffer dries up the client pins to the last known target rather than guess.
- Any language rewrite (e.g. Rust pyo3) — per CLAUDE.md §Language fit, the bottleneck is architecture, not Python runtime.

---

## File Structure

### New files

| Path | Responsibility |
|---|---|
| `backend/app/services/sim_lock.py` | Module-level `threading.RLock` + `read()` / `write()` context managers. Single source of truth for PUT-vs-tick serialization. |
| `backend/app/services/broadcaster.py` | Pub-sub: `subscribe()` returns a `queue.Queue`, `publish(payload)` fans out to all queues. In-process only (single-worker deployment per §8.1). |
| `backend/app/routes/stream.py` | New blueprint route `GET /api/v1/world/stream` → text/event-stream generator consuming from broadcaster. |
| `frontend/src/api/stream.ts` | `EventSource` wrapper with reconnect + a `status` observable (`'connected' \| 'reconnecting' \| 'fallback'`). |
| `frontend/src/render/interpBuffer.ts` | 2-snapshot ring with `push(snap)` + `sampleAt(serverTimeMs)` → per-agent positions. Pure, no DOM. |
| `frontend/src/render/ease.ts` | `easeOutCubic(t: number): number`. Pure. |
| `frontend/src/render/lifecycleFade.ts` | Per-agent fade state map; `update(agentIds, now)` + `alphaFor(id, now)`. Pure. |

### Modified files

| Path | Change |
|---|---|
| `backend/app/services/simulation_service.py` | Wrap `create_simulation` with `sim_lock.write()`; wrap `step_simulation` with `sim_lock.read()`. Compute `server_time_ms_at_tick`. |
| `backend/app/routes/simulation.py:79-142,205-243` | `PUT /simulation` acquires `sim_lock.write()`. `GET /world/state` emits `server_time_ms` + `tick_ms`. |
| `backend/app/routes/serializers.py` | `simulation_summary` adds `server_time_ms`, `tick_ms`. |
| `backend/app/services/tick_loop.py:113-138` | After successful tick, call `broadcaster.publish(world_state_payload)`. |
| `backend/app/app.py` | Register new `stream` blueprint under `/api/v1`. |
| `frontend/src/api/queries.ts` | Add `useWorldStream()` hook; existing poll hook unchanged. |
| `frontend/src/api/types.ts` | `WorldStateResponse.sim` adds `server_time_ms: number`, `tick_ms: number`. |
| `frontend/src/components/WorldCanvas.tsx:68-138,187-205` | Feed either stream or poll snapshots into `InterpBuffer`; rAF loop samples buffer at `performance.now() - INTERP_DELAY_MS`. |
| `frontend/src/render/Canvas2DRenderer.ts:149-253,486-495` | Replace hand-rolled `prevPositions`/`alpha`/EMA logic with output from interp buffer. Apply `easeOutCubic` to the fractional component. Widen snap-guard `<= 2` to `<= 8`. Multiply body draw alpha by `lifecycleFade.alphaFor(id, now)`. |

### Test files

| Path | Covers |
|---|---|
| `backend/tests/services/test_sim_lock.py` (NEW) | `read()` / `write()` mutual exclusion; re-entrancy. |
| `backend/tests/services/test_simulation_service_race.py` (NEW) | PUT concurrent with tick → no FK violation, tick_loop survives, final state is new sim. |
| `backend/tests/services/test_broadcaster.py` (NEW) | Fan-out; slow subscriber doesn't block publisher; unsubscribe releases queue. |
| `backend/tests/routes/test_stream.py` (NEW) | SSE response shape (`text/event-stream`), one `tick` event per publish, heartbeat. |
| `backend/tests/services/test_serializers.py` (MODIFY) | `simulation_summary` contains `server_time_ms`, `tick_ms`. |
| `frontend/src/render/ease.test.ts` (NEW) | `easeOutCubic(0)=0`, `(1)=1`, `(0.5) ≈ 0.875`. |
| `frontend/src/render/interpBuffer.test.ts` (NEW) | Bracketing, out-of-range sample behavior, per-agent missing in one snap. |
| `frontend/src/render/lifecycleFade.test.ts` (NEW) | Appear → 0→1 over 250ms cubic; disappear → 1→0 over 250ms cubic; id retained until fade-out completes. |
| `frontend/src/render/Canvas2DRenderer.test.ts` (MODIFY) | Snap-guard threshold 8 test; fade alpha reaches body draw path. |
| `frontend/src/api/stream.test.ts` (NEW) | Reconnect after error; status transitions; message parsing. |

---

## Task list (16 tasks)

### Task 1: Backend — repro test for the PUT-vs-tick FK race

**Files:**
- Test: `backend/tests/services/test_simulation_service_race.py` (new)

- [ ] **Step 1: Write the failing test**

```python
"""Regression: PUT /simulation concurrent with a tick_loop iteration must
not leave the session with pending event rows that reference agent ids
from the pre-PUT sim. Reproduces the FK violation captured in
scripts/repro_put_race.py."""
import threading
import time

from app.services import simulation_service


def _create_small_sim():
    return simulation_service.create_simulation(
        width=8, height=8, seed=1,
        colonies=2, agents_per_colony=2,
    )


def test_put_during_tick_does_not_raise_fk(app, db_session):
    del db_session  # fixture triggers TRUNCATE + cache reset; no direct use
    with app.app_context():
        _create_small_sim()

    # Thread A: keeps stepping the sim.
    stop_stepper = threading.Event()
    stepper_errors = []

    def stepper():
        while not stop_stepper.is_set():
            try:
                with app.app_context():
                    simulation_service.step_simulation(ticks=1)
            except Exception as e:
                stepper_errors.append(e)
                return

    t = threading.Thread(target=stepper, daemon=True)
    t.start()
    time.sleep(0.2)  # let stepper run several ticks

    # Thread B (this thread): PUT a fresh sim.
    with app.app_context():
        _create_small_sim()

    stop_stepper.set()
    t.join(timeout=2.0)
    assert stepper_errors == [], (
        f'tick_loop crashed during concurrent PUT: {stepper_errors}'
    )
```

- [ ] **Step 2: Run test to verify it fails (confirming the race exists)**

Run: `docker compose exec -T flask pytest tests/services/test_simulation_service_race.py -v`

Expected: FAIL with `sqlalchemy.exc.IntegrityError ... ForeignKeyViolation ... events_agent_id_fkey`.

- [ ] **Step 3: Commit the repro (red)**

```bash
git add backend/tests/services/test_simulation_service_race.py
git commit -m "test(services): repro PUT-vs-tick FK race"
```

---

### Task 2: Backend — `sim_lock` module

**Files:**
- Create: `backend/app/services/sim_lock.py`
- Test: `backend/tests/services/test_sim_lock.py` (new)

- [ ] **Step 1: Write the failing test**

```python
"""sim_lock: a module-level RLock with read()/write() context managers.

Both are re-entrant on the same thread (RLock); write excludes concurrent
reads and other writes. We only need one writer semantic here — a
full reader-writer lock is overkill for a single-worker deployment with
one tick loop thread."""
import threading
import time

from app.services import sim_lock


def test_write_excludes_concurrent_read():
    """If one thread holds write(), another thread entering read() blocks."""
    started = threading.Event()
    holding_write = threading.Event()
    observed = []

    def writer():
        with sim_lock.write():
            holding_write.set()
            time.sleep(0.1)
            observed.append('writer-done')

    def reader():
        started.set()
        with sim_lock.read():
            observed.append('reader-inside')

    holding_write.clear()
    tw = threading.Thread(target=writer)
    tw.start()
    holding_write.wait(1.0)
    assert holding_write.is_set()

    tr = threading.Thread(target=reader)
    tr.start()
    started.wait(1.0)
    tw.join(1.0)
    tr.join(1.0)

    # Writer must finish before reader enters.
    assert observed == ['writer-done', 'reader-inside']


def test_write_is_reentrant_on_same_thread():
    """A single thread that already holds write() can re-enter write()
    (e.g. a nested create_simulation call in tests). RLock semantics."""
    with sim_lock.write():
        with sim_lock.write():
            pass  # should not deadlock


def test_read_is_reentrant_on_same_thread():
    with sim_lock.read():
        with sim_lock.read():
            pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec -T flask pytest tests/services/test_sim_lock.py -v`

Expected: FAIL with `ImportError` or `AttributeError` — module doesn't exist yet.

- [ ] **Step 3: Write the minimal implementation**

Create `backend/app/services/sim_lock.py`:

```python
"""Single source of truth for serializing sim-mutating requests against
the background tick loop.

Problem this solves:
  PUT /simulation wipes (`DELETE FROM agents`) and rebuilds the sim. If
  the tick loop is mid-tick with the old in-memory Simulation object,
  its ORM session has pending Event rows referencing old `agent.id`s.
  The PUT commits the DELETE before the tick loop's autoflush runs;
  autoflush then INSERTs events with stale agent_ids → FK violation →
  5 consecutive failures → auto-pause. See scripts/repro_put_race.py.

Why an RLock and not a ReadWriteLock:
  We have one writer (PUT) and one reader (tick_loop thread). Under that
  shape a plain RLock used with `write()` always and `read()` never
  concurrent with `write()` is functionally correct and trivial to
  reason about. Upgrading to a proper RW lock is a 5-line change if a
  second reader ever appears.

Re-entrancy matters: `create_simulation` may call itself (tests) or be
called from a handler that has already acquired write() — RLock lets
that work instead of deadlocking.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager

_lock = threading.RLock()


@contextmanager
def read():
    """Acquire for read. Blocks if a writer holds the lock."""
    _lock.acquire()
    try:
        yield
    finally:
        _lock.release()


@contextmanager
def write():
    """Acquire for write. Excludes concurrent readers AND other writers."""
    _lock.acquire()
    try:
        yield
    finally:
        _lock.release()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec -T flask pytest tests/services/test_sim_lock.py -v`

Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/sim_lock.py backend/tests/services/test_sim_lock.py
git commit -m "feat(services): sim_lock read/write context managers"
```

---

### Task 3: Backend — wire `sim_lock` into `create_simulation` + `step_simulation`

**Files:**
- Modify: `backend/app/services/simulation_service.py:132-210,213-280`

- [ ] **Step 1: Wrap `create_simulation`'s transactional body under `sim_lock.write()`**

Find the function at `backend/app/services/simulation_service.py:132`. Wrap the `try:` block (lines 151-207) so the WHOLE wipe-rebuild-commit happens under the write lock. Also import `sim_lock`.

Add at top of file (near other imports):

```python
from . import sim_lock
```

Change the function body. The current body at lines 151-207 looks like:

```python
    try:
        db.session.query(models.Event).delete()
        ...
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    _current_sim = sim
    return sim
```

After the change:

```python
    with sim_lock.write():
        try:
            db.session.query(models.Event).delete()
            db.session.query(models.Agent).delete()
            db.session.query(models.WorldTile).delete()
            db.session.query(models.Colony).delete()
            db.session.query(models.SimulationState).delete()
            db.session.flush()

            if colonies and agents_per_colony is not None:
                engine_colonies = _build_default_colonies(width, height, colonies)
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
                    agent_count=agent_count,
                )

            sim.current_tick = cycle.TICKS_PER_PHASE

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

- [ ] **Step 2: Wrap `step_simulation` body under `sim_lock.read()`**

Find the function at `backend/app/services/simulation_service.py:213`. Wrap the body that touches `sim` and the DB:

Current body at lines 224-280 looks like:

```python
def step_simulation(ticks=1):
    ...
    sim = get_current_simulation()
    try:
        events = sim.run(ticks)
        ...
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return events
```

After:

```python
def step_simulation(ticks=1):
    """..."""
    if not isinstance(ticks, int) or ticks < 1:
        raise ValueError(f'ticks must be a positive int, got {ticks!r}')
    if ticks > MAX_TICKS_PER_STEP:
        raise ValueError(
            f'ticks={ticks} exceeds MAX_TICKS_PER_STEP={MAX_TICKS_PER_STEP}'
        )
    with sim_lock.read():
        sim = get_current_simulation()
        try:
            events = sim.run(ticks)

            event_rows = [mappers.event_to_row(e) for e in events]
            db.session.add_all(event_rows)

            dirty_tile_coords = {
                (e['data']['tile_x'], e['data']['tile_y'])
                for e in events
                if e['type'] in ('foraged', 'planted', 'harvested', 'crop_matured')
            }
            if dirty_tile_coords:
                _update_dirty_tiles(sim, dirty_tile_coords)

            dirty_colony_ids = {
                e['data']['colony_id']
                for e in events
                if e['type'] in ('harvested', 'ate_from_cache', 'deposited')
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
```

- [ ] **Step 3: Run the race repro test from Task 1**

Run: `docker compose exec -T flask pytest tests/services/test_simulation_service_race.py -v`

Expected: PASS. The FK violation no longer occurs because the PUT and the tick are now mutually exclusive.

- [ ] **Step 4: Run the full backend suite to confirm no regressions**

Run: `docker compose exec -T flask pytest`

Expected: all green (252 + 3 new from Tasks 1+2 = 255).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/simulation_service.py
git commit -m "fix(services): serialize PUT vs tick_loop under sim_lock"
```

---

### Task 4: Backend — add `server_time_ms` + `tick_ms` to the wire snapshot

**Files:**
- Modify: `backend/app/routes/serializers.py` (in `simulation_summary`)
- Modify: `backend/app/services/tick_loop.py` (record `last_tick_ms` on each advance)
- Modify: `backend/app/services/simulation_service.py` (store `last_tick_ms`)
- Test: `backend/tests/services/test_serializers.py` (modify)

Why: the client needs a monotonic server timestamp per tick so it can render at `serverTime - INTERP_DELAY_MS` independent of network jitter.

- [ ] **Step 1: Add the failing test**

Append to `backend/tests/services/test_serializers.py`:

```python
def test_simulation_summary_includes_server_time_ms(app):
    """Snapshot must carry a monotonic server timestamp (ms) and the
    wall-clock ms at which the current tick was produced. The client
    uses these to place ticks on its own time axis."""
    with app.app_context():
        from app.services import simulation_service, serializers
        sim = simulation_service.create_simulation(
            width=4, height=4, seed=1, agent_count=1,
        )
        control = simulation_service.get_simulation_control()
        summary = serializers.simulation_summary(sim, control)
    assert 'server_time_ms' in summary
    assert 'tick_ms' in summary
    assert isinstance(summary['server_time_ms'], int)
    assert isinstance(summary['tick_ms'], int)
    assert summary['server_time_ms'] >= summary['tick_ms']
```

- [ ] **Step 2: Run to verify fail**

Run: `docker compose exec -T flask pytest tests/services/test_serializers.py::test_simulation_summary_includes_server_time_ms -v`

Expected: FAIL with `KeyError` or `assert 'server_time_ms' in summary`.

- [ ] **Step 3: Add `last_tick_ms` capture to `simulation_service.step_simulation`**

Add module-level state near the top of `backend/app/services/simulation_service.py` (near `_current_sim`):

```python
import time as _time
_last_tick_ms: int = 0  # monotonic ms at which the most recent tick completed
```

Inside `step_simulation`, after `db.session.commit()` and before the function returns (still inside the `with sim_lock.read():` block), add:

```python
            global _last_tick_ms
            _last_tick_ms = _monotonic_ms()
```

Add a helper near the top of the module:

```python
def _monotonic_ms() -> int:
    """Monotonic clock in integer milliseconds. Safe for cross-tick
    deltas — `time.monotonic()` is guaranteed non-decreasing across
    calls in one process. We coerce to int so the wire shape is
    trivially JSON-serializable without float precision surprises."""
    return int(_time.monotonic() * 1000)


def get_last_tick_ms() -> int:
    return _last_tick_ms
```

- [ ] **Step 4: Extend `simulation_summary` to include the new fields**

Find `simulation_summary` in `backend/app/routes/serializers.py`. It currently returns a dict of sim-level fields. Add `server_time_ms` + `tick_ms` entries.

```python
def simulation_summary(sim, control):
    from . import simulation_service  # local import avoids cycle
    now_ms = simulation_service._monotonic_ms()
    tick_ms = simulation_service.get_last_tick_ms() or now_ms
    return {
        'tick': sim.current_tick,
        'seed': sim.world.seed,  # or however it currently reads seed
        'width': sim.world.width,
        'height': sim.world.height,
        'agent_count': len(sim.agents),
        'alive_count': sum(1 for a in sim.agents if a.alive),
        'running': control['running'],
        'speed': control['speed'],
        'day': cycle.day_of(sim.current_tick),     # existing helper
        'phase': cycle.phase_of(sim.current_tick), # existing helper
        'server_time_ms': now_ms,
        'tick_ms': tick_ms,
    }
```

(Read the existing function first and only add the two new keys; keep every other field identical to avoid regressions in the ~60 existing tests that snapshot this shape.)

- [ ] **Step 5: Run the new test + full suite**

```
docker compose exec -T flask pytest tests/services/test_serializers.py -v
docker compose exec -T flask pytest
```

Expected: new test PASS; full suite 256 green (252 + race + new serializer test).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/simulation_service.py backend/app/routes/serializers.py backend/tests/services/test_serializers.py
git commit -m "feat(services,api): surface server_time_ms + tick_ms on wire"
```

---

### Task 5: Backend — pub-sub broadcaster for tick events

**Files:**
- Create: `backend/app/services/broadcaster.py`
- Test: `backend/tests/services/test_broadcaster.py` (new)

Why: the SSE route needs to emit a frame per tick without polling. A publisher (tick_loop) pushes; subscribers (each SSE connection) pull from their own queue.

- [ ] **Step 1: Write the failing test**

```python
"""Broadcaster: fan-out pub-sub inside a single process."""
import queue
import threading
import time

from app.services import broadcaster


def test_subscribe_receives_publish():
    q = broadcaster.subscribe()
    try:
        broadcaster.publish({'tick': 1})
        msg = q.get(timeout=1.0)
        assert msg == {'tick': 1}
    finally:
        broadcaster.unsubscribe(q)


def test_multiple_subscribers_each_get_copy():
    q1 = broadcaster.subscribe()
    q2 = broadcaster.subscribe()
    try:
        broadcaster.publish({'tick': 5})
        assert q1.get(timeout=1.0) == {'tick': 5}
        assert q2.get(timeout=1.0) == {'tick': 5}
    finally:
        broadcaster.unsubscribe(q1)
        broadcaster.unsubscribe(q2)


def test_slow_subscriber_does_not_block_publisher():
    """If a subscriber's queue hits its bound, the publisher drops the
    message for that subscriber rather than blocking. We never want one
    dead browser tab to freeze the tick loop."""
    q = broadcaster.subscribe(maxsize=2)
    try:
        broadcaster.publish({'n': 1})
        broadcaster.publish({'n': 2})
        # Third publish finds q full. Must not block.
        t0 = time.monotonic()
        broadcaster.publish({'n': 3})
        assert time.monotonic() - t0 < 0.2, 'publish blocked waiting for slow subscriber'
    finally:
        broadcaster.unsubscribe(q)


def test_unsubscribe_stops_delivery():
    q = broadcaster.subscribe()
    broadcaster.unsubscribe(q)
    broadcaster.publish({'n': 1})
    assert q.empty()
```

- [ ] **Step 2: Run to verify fail**

Run: `docker compose exec -T flask pytest tests/services/test_broadcaster.py -v`

Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement**

Create `backend/app/services/broadcaster.py`:

```python
"""In-process pub-sub for tick snapshots.

One publisher (the tick loop) fans out to N subscribers (one per live
SSE connection). Bounded queue per subscriber: if a client tab is
backgrounded or stalls, the publisher drops that subscriber's message
instead of blocking the tick loop. Single-worker deployment (§8.1)
means no cross-process broadcast needed — a simple list of queues is
the whole implementation.
"""
from __future__ import annotations

import queue
import threading
from typing import Any

_subscribers_lock = threading.Lock()
_subscribers: list[queue.Queue[Any]] = []


def subscribe(maxsize: int = 8) -> queue.Queue:
    """Register a new subscriber. Returned queue receives every
    subsequent publish. Caller is responsible for calling unsubscribe()
    when done (typically in a finally clause of a stream handler)."""
    q: queue.Queue = queue.Queue(maxsize=maxsize)
    with _subscribers_lock:
        _subscribers.append(q)
    return q


def unsubscribe(q: queue.Queue) -> None:
    with _subscribers_lock:
        try:
            _subscribers.remove(q)
        except ValueError:
            pass


def publish(payload: Any) -> None:
    """Fan out payload to every subscriber. A full queue drops the
    message for that subscriber; the next publish will catch them up.
    Never blocks."""
    with _subscribers_lock:
        snapshot = list(_subscribers)
    for q in snapshot:
        try:
            q.put_nowait(payload)
        except queue.Full:
            pass
```

- [ ] **Step 4: Run to verify pass**

Run: `docker compose exec -T flask pytest tests/services/test_broadcaster.py -v`

Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/broadcaster.py backend/tests/services/test_broadcaster.py
git commit -m "feat(services): in-process broadcaster for tick pub-sub"
```

---

### Task 6: Backend — publish snapshot from `tick_loop` after each tick

**Files:**
- Modify: `backend/app/services/tick_loop.py:113-138`
- Test: `backend/tests/services/test_tick_loop_broadcast.py` (new)

- [ ] **Step 1: Write the failing test**

```python
"""Each successful tick pushes one snapshot onto the broadcaster."""
from app.services import broadcaster, tick_loop


def test_single_tick_publishes_one_payload(app, monkeypatch):
    """After a successful stepper call, _single_tick publishes exactly
    one snapshot with the post-tick state."""
    payloads = []
    real_publish = broadcaster.publish
    monkeypatch.setattr(
        broadcaster, 'publish',
        lambda payload: (payloads.append(payload), real_publish(payload)) and None,
    )
    with app.app_context():
        from app.services import simulation_service
        simulation_service.create_simulation(
            width=4, height=4, seed=1, agent_count=1,
        )
        simulation_service.update_simulation_control(running=True, speed=1.0)
        tick_loop._single_tick(
            control_provider=simulation_service.get_simulation_control,
            stepper=simulation_service.step_simulation,
            pause_on_fatal=lambda: None,
        )
    assert len(payloads) == 1
    assert 'sim' in payloads[0]
    assert 'agents' in payloads[0]
    assert payloads[0]['sim']['server_time_ms'] > 0


def test_tick_failure_does_not_publish(app, monkeypatch):
    payloads = []
    monkeypatch.setattr(broadcaster, 'publish', payloads.append)
    def fail(**_kw):
        raise RuntimeError('boom')
    with app.app_context():
        from app.services import simulation_service
        simulation_service.create_simulation(
            width=4, height=4, seed=1, agent_count=1,
        )
        simulation_service.update_simulation_control(running=True, speed=1.0)
        tick_loop._single_tick(
            control_provider=simulation_service.get_simulation_control,
            stepper=fail,
            pause_on_fatal=lambda: None,
        )
    assert payloads == []
```

- [ ] **Step 2: Run to verify fail**

Run: `docker compose exec -T flask pytest tests/services/test_tick_loop_broadcast.py -v`

Expected: FAIL — publish is never called.

- [ ] **Step 3: Implement in `tick_loop._single_tick`**

Edit `backend/app/services/tick_loop.py`. Add at the top:

```python
from . import broadcaster, serializers
```

Inside `_single_tick`, after the successful `stepper(ticks=1)` line (after the `_consecutive_failures = 0` reset on the success path), publish the payload. The current success-path tail looks like:

```python
    _consecutive_failures = 0
    speed = max(control['speed'], simulation_service.MIN_SPEED)
    return max(MIN_INTERVAL, 1.0 / speed)
```

Change to:

```python
    _consecutive_failures = 0
    try:
        sim = simulation_service.get_current_simulation()
        control_after = simulation_service.get_simulation_control()
        payload = {
            'sim': serializers.simulation_summary(sim, control_after),
            'world': serializers.world_to_dict(sim.world),
            'agents': [serializers.agent_to_dict(a) for a in sim.agents],
            'colonies': [
                serializers.colony_to_dict(c)
                for c in sorted(sim.colonies.values(), key=lambda c: c.id)
            ],
        }
        broadcaster.publish(payload)
    except Exception:
        logger.exception('tick_loop: broadcast failed — skipping this tick')
    speed = max(control['speed'], simulation_service.MIN_SPEED)
    return max(MIN_INTERVAL, 1.0 / speed)
```

Rationale for the try-wrap: a serializer exception must not cascade into `_consecutive_failures` accounting — that counter is for tick *work*, not for broadcast failures.

- [ ] **Step 4: Run the test**

Run: `docker compose exec -T flask pytest tests/services/test_tick_loop_broadcast.py -v`

Expected: PASS (2 tests).

- [ ] **Step 5: Run full suite**

Run: `docker compose exec -T flask pytest`

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/tick_loop.py backend/tests/services/test_tick_loop_broadcast.py
git commit -m "feat(tick_loop): publish snapshot to broadcaster on successful tick"
```

---

### Task 7: Backend — SSE route `/api/v1/world/stream`

**Files:**
- Create: `backend/app/routes/stream.py`
- Modify: `backend/app/app.py` (register blueprint)
- Test: `backend/tests/routes/test_stream.py` (new)

- [ ] **Step 1: Write the failing test**

```python
"""SSE endpoint streams one event per tick. Content-Type is
text/event-stream; each message is a `data: <json>\\n\\n` frame."""
import json
import threading
import time

from app.services import broadcaster


def test_stream_emits_frame_per_publish(app, client):
    """Hit /world/stream, publish one frame, assert we receive it."""
    results = {}

    def consume():
        with client.get('/api/v1/world/stream', buffered=False) as resp:
            assert resp.status_code == 200
            assert resp.mimetype == 'text/event-stream'
            # Read the first data frame.
            for raw in resp.response:
                chunk = raw.decode('utf-8')
                if chunk.startswith('data: '):
                    payload = json.loads(chunk[len('data: '):].strip())
                    results['payload'] = payload
                    return

    t = threading.Thread(target=consume, daemon=True)
    t.start()
    time.sleep(0.1)  # let the consumer subscribe
    broadcaster.publish({'tick': 42, 'hello': 'world'})
    t.join(timeout=2.0)
    assert results.get('payload') == {'tick': 42, 'hello': 'world'}
```

- [ ] **Step 2: Run to verify fail**

Run: `docker compose exec -T flask pytest tests/routes/test_stream.py -v`

Expected: FAIL (route not registered → 404).

- [ ] **Step 3: Implement the stream blueprint**

Create `backend/app/routes/stream.py`:

```python
"""Server-Sent Events endpoint for tick pushes.

Why SSE and not WS:
  * One-way push (server → client) is all we need — the observer never
    talks back through this channel.
  * SSE is plain HTTP + Content-Type: text/event-stream; no handshake,
    no framing protocol, no extra dependency.
  * Browsers auto-reconnect (EventSource retries with exponential
    backoff). We still expose a status observable on the client for UI.

Transport shape:
  Each tick → one `data: <json>\\n\\n` chunk. JSON is the same shape as
  GET /world/state so the client can use one normalizer. Heartbeat
  comment every 15 s to keep intermediaries from closing the socket
  (nginx proxy_read_timeout default 60 s).
"""
from __future__ import annotations

import json
import queue
import time

from flask import Blueprint, Response, stream_with_context

from app.services import broadcaster


bp = Blueprint('stream', __name__)

_HEARTBEAT_INTERVAL_S = 15.0


@bp.get('/world/stream')
def world_stream():
    q = broadcaster.subscribe()

    @stream_with_context
    def gen():
        try:
            last_heartbeat = time.monotonic()
            while True:
                try:
                    payload = q.get(timeout=1.0)
                except queue.Empty:
                    now = time.monotonic()
                    if now - last_heartbeat >= _HEARTBEAT_INTERVAL_S:
                        yield ': heartbeat\n\n'
                        last_heartbeat = now
                    continue
                # SSE frame: single-line data field with JSON body.
                yield f'data: {json.dumps(payload)}\n\n'
                last_heartbeat = time.monotonic()
        finally:
            broadcaster.unsubscribe(q)

    return Response(
        gen(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',  # nginx: don't buffer this response
            'Connection': 'keep-alive',
        },
    )
```

Edit `backend/app/app.py` to register the new blueprint. Find the `register_blueprint` line for the simulation blueprint (`app.register_blueprint(simulation_bp, url_prefix="/api/v1")` at line 50) and add below it:

```python
    from app.routes.stream import bp as stream_bp
    app.register_blueprint(stream_bp, url_prefix='/api/v1')
```

- [ ] **Step 4: Run the test**

Run: `docker compose exec -T flask pytest tests/routes/test_stream.py -v`

Expected: PASS.

- [ ] **Step 5: Smoke-test the live server**

```bash
docker compose exec -T flask curl -sN --max-time 3 http://localhost:5000/api/v1/world/stream | head -20 || true
```

Expected: (no data without a sim running; may just hang until timeout — that's fine, confirms the connection held open).

- [ ] **Step 6: Update nginx to not buffer SSE**

Inspect `nginx/default.conf` (or similar). For the `/api/` location, add if absent:

```nginx
proxy_buffering off;
proxy_cache off;
```

Also raise `proxy_read_timeout 3600s` so a quiet SSE stream isn't culled between heartbeats.

Then `docker compose restart nginx`.

- [ ] **Step 7: Commit**

```bash
git add backend/app/routes/stream.py backend/app/app.py backend/tests/routes/test_stream.py nginx/default.conf
git commit -m "feat(routes): SSE endpoint /world/stream with heartbeat"
```

---

### Task 8: Frontend — `EventSource` wrapper with reconnect + fallback signal

**Files:**
- Create: `frontend/src/api/stream.ts`
- Test: `frontend/src/api/stream.test.ts` (new)

- [ ] **Step 1: Write the failing test**

```ts
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { connectWorldStream, type StreamStatus } from './stream';

// Minimal EventSource stub so the test controls the lifecycle.
class FakeEventSource {
  static instances: FakeEventSource[] = [];
  url: string;
  onmessage: ((e: MessageEvent) => void) | null = null;
  onerror: ((e: Event) => void) | null = null;
  onopen: ((e: Event) => void) | null = null;
  readyState = 0;
  closed = false;

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }
  close() { this.closed = true; this.readyState = 2; }
}

describe('connectWorldStream', () => {
  beforeEach(() => {
    FakeEventSource.instances.length = 0;
    (globalThis as any).EventSource = FakeEventSource;
  });
  afterEach(() => {
    delete (globalThis as any).EventSource;
  });

  it('delivers parsed JSON payloads via onMessage', () => {
    const messages: unknown[] = [];
    connectWorldStream({
      url: '/api/v1/world/stream',
      onMessage: m => messages.push(m),
      onStatus: () => {},
    });
    const es = FakeEventSource.instances[0];
    es.onopen?.(new Event('open'));
    es.onmessage?.({ data: JSON.stringify({ tick: 7 }) } as MessageEvent);
    expect(messages).toEqual([{ tick: 7 }]);
  });

  it('emits status connected → reconnecting → fallback after repeated errors', () => {
    const statuses: StreamStatus[] = [];
    const conn = connectWorldStream({
      url: '/api/v1/world/stream',
      onMessage: () => {},
      onStatus: s => statuses.push(s),
      fallbackAfterFailures: 3,
    });
    const es1 = FakeEventSource.instances[0];
    es1.onopen?.(new Event('open'));
    es1.onerror?.(new Event('error'));
    es1.onerror?.(new Event('error'));
    es1.onerror?.(new Event('error'));
    expect(statuses).toContain('connected');
    expect(statuses).toContain('reconnecting');
    expect(statuses[statuses.length - 1]).toBe('fallback');
    conn.close();
  });
});
```

- [ ] **Step 2: Run to verify fail**

Run: `cd frontend && npx vitest run src/api/stream.test.ts`

Expected: FAIL (module not found).

- [ ] **Step 3: Implement the wrapper**

Create `frontend/src/api/stream.ts`:

```ts
// Thin EventSource wrapper with a status observable.
//
// Why this layer exists:
//  * EventSource auto-reconnects on network blip but stays silent about
//    it — a paused sim for 15 min would tear down the proxy and the UI
//    wouldn't know to show "reconnecting". We surface that state.
//  * On repeated errors we trip a `fallback` status so WorldCanvas can
//    switch back to the 500 ms REST poll — e.g., the nginx micro-cache
//    eating SSE in some deploy environment.

export type StreamStatus = 'connecting' | 'connected' | 'reconnecting' | 'fallback';

export interface StreamConn {
  close(): void;
}

export interface StreamOpts<T> {
  url: string;
  onMessage: (payload: T) => void;
  onStatus: (status: StreamStatus) => void;
  fallbackAfterFailures?: number;
}

export function connectWorldStream<T = unknown>(opts: StreamOpts<T>): StreamConn {
  const fallbackAt = opts.fallbackAfterFailures ?? 5;
  let failures = 0;
  let es: EventSource | null = null;
  let closed = false;

  const open = () => {
    if (closed) return;
    opts.onStatus(failures === 0 ? 'connecting' : 'reconnecting');
    es = new EventSource(opts.url);
    es.onopen = () => {
      failures = 0;
      opts.onStatus('connected');
    };
    es.onmessage = (e: MessageEvent) => {
      try {
        opts.onMessage(JSON.parse(e.data) as T);
      } catch {
        // Malformed frame — log and ignore.
        // eslint-disable-next-line no-console
        console.warn('[stream] malformed frame', e.data);
      }
    };
    es.onerror = () => {
      failures += 1;
      es?.close();
      if (failures >= fallbackAt) {
        opts.onStatus('fallback');
        return; // stop retrying; WorldCanvas switches to poll
      }
      opts.onStatus('reconnecting');
      // Browsers already auto-reconnect. We close + reopen to ensure a
      // fresh connection attempt with our own backoff.
      setTimeout(open, Math.min(5000, 200 * 2 ** failures));
    };
  };

  open();

  return {
    close() {
      closed = true;
      es?.close();
    },
  };
}
```

- [ ] **Step 4: Run to verify pass**

Run: `cd frontend && npx vitest run src/api/stream.test.ts`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/stream.ts frontend/src/api/stream.test.ts
git commit -m "feat(api): EventSource wrapper with status + fallback signal"
```

---

### Task 9: Frontend — `easeOutCubic` pure function

**Files:**
- Create: `frontend/src/render/ease.ts`
- Test: `frontend/src/render/ease.test.ts` (new)

- [ ] **Step 1: Write the failing test**

```ts
import { describe, it, expect } from 'vitest';
import { easeOutCubic } from './ease';

describe('easeOutCubic', () => {
  it('hits 0 at t=0', () => {
    expect(easeOutCubic(0)).toBe(0);
  });
  it('hits 1 at t=1', () => {
    expect(easeOutCubic(1)).toBe(1);
  });
  it('is past the midpoint at t=0.5 (biased toward arrival)', () => {
    const y = easeOutCubic(0.5);
    expect(y).toBeGreaterThan(0.8);
    expect(y).toBeLessThan(0.9);
  });
  it('clamps inputs outside [0,1]', () => {
    expect(easeOutCubic(-0.5)).toBe(0);
    expect(easeOutCubic(1.5)).toBe(1);
  });
});
```

- [ ] **Step 2: Run fail**

Run: `cd frontend && npx vitest run src/render/ease.test.ts`

Expected: FAIL (module not found).

- [ ] **Step 3: Implement**

Create `frontend/src/render/ease.ts`:

```ts
// Ease-out cubic: y = 1 - (1 - t)^3.
// At t=0.5, y ≈ 0.875 — the body has already covered most of its
// travel early in the tick window, producing an arrival-biased motion
// that reads as biological instead of mechanical.
export function easeOutCubic(t: number): number {
  if (t <= 0) return 0;
  if (t >= 1) return 1;
  const inv = 1 - t;
  return 1 - inv * inv * inv;
}
```

- [ ] **Step 4: Run pass**

Run: `cd frontend && npx vitest run src/render/ease.test.ts`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/render/ease.ts frontend/src/render/ease.test.ts
git commit -m "feat(render): easeOutCubic pure function"
```

---

### Task 10: Frontend — `InterpBuffer` (2-snapshot ring + time-based sampling)

**Files:**
- Create: `frontend/src/render/interpBuffer.ts`
- Test: `frontend/src/render/interpBuffer.test.ts` (new)

Why separate from Canvas2DRenderer: the buffer is pure data — no canvas, no animation config — and it is the piece most likely to need tweaks after visual QA. Keeping it isolated lets us unit-test every branch without mocking the renderer.

- [ ] **Step 1: Write the failing test**

```ts
import { describe, it, expect } from 'vitest';
import { InterpBuffer, type Snap, type AgentSample } from './interpBuffer';

function snap(serverTimeMs: number, tick: number, agents: AgentSample[]): Snap {
  return { serverTimeMs, tick, agents };
}

describe('InterpBuffer', () => {
  it('returns targets exactly when renderTime matches a known snap', () => {
    const buf = new InterpBuffer();
    buf.push(snap(1000, 1, [{ id: 7, x: 0, y: 0 }]));
    buf.push(snap(2000, 2, [{ id: 7, x: 3, y: 0 }]));
    const out = buf.sampleAt(2000);
    expect(out.positions.get(7)).toEqual({ x: 3, y: 0, alphaRaw: 1 });
  });

  it('interpolates linearly between two snapshots', () => {
    const buf = new InterpBuffer();
    buf.push(snap(1000, 1, [{ id: 1, x: 0, y: 0 }]));
    buf.push(snap(2000, 2, [{ id: 1, x: 10, y: 0 }]));
    const out = buf.sampleAt(1500);
    const pos = out.positions.get(1)!;
    expect(pos.x).toBeCloseTo(5, 5);
    expect(pos.alphaRaw).toBeCloseTo(0.5, 5);
  });

  it('pins to older snap when renderTime is before buffer', () => {
    const buf = new InterpBuffer();
    buf.push(snap(1000, 1, [{ id: 1, x: 0, y: 0 }]));
    buf.push(snap(2000, 2, [{ id: 1, x: 10, y: 0 }]));
    const out = buf.sampleAt(500); // before
    expect(out.positions.get(1)).toEqual({ x: 0, y: 0, alphaRaw: 0 });
  });

  it('pins to newer snap when renderTime is past buffer', () => {
    const buf = new InterpBuffer();
    buf.push(snap(1000, 1, [{ id: 1, x: 0, y: 0 }]));
    buf.push(snap(2000, 2, [{ id: 1, x: 10, y: 0 }]));
    const out = buf.sampleAt(9000); // long after
    expect(out.positions.get(1)).toEqual({ x: 10, y: 0, alphaRaw: 1 });
  });

  it('keeps only last 2 snapshots', () => {
    const buf = new InterpBuffer();
    buf.push(snap(1000, 1, [{ id: 1, x: 0, y: 0 }]));
    buf.push(snap(2000, 2, [{ id: 1, x: 10, y: 0 }]));
    buf.push(snap(3000, 3, [{ id: 1, x: 20, y: 0 }]));
    // After third push, oldest (t=1000) is evicted. Interpolate 2→3.
    const out = buf.sampleAt(2500);
    expect(out.positions.get(1)!.x).toBeCloseTo(15, 5);
  });

  it('reports agents present in newer but not older as newlyPresent', () => {
    const buf = new InterpBuffer();
    buf.push(snap(1000, 1, [{ id: 1, x: 0, y: 0 }]));
    buf.push(snap(2000, 2, [{ id: 1, x: 10, y: 0 }, { id: 2, x: 5, y: 5 }]));
    const out = buf.sampleAt(1500);
    expect(out.newlyPresent).toContain(2);
    expect(out.positions.get(2)).toEqual({ x: 5, y: 5, alphaRaw: 1 });
  });

  it('reports agents present in older but not newer as departed', () => {
    const buf = new InterpBuffer();
    buf.push(snap(1000, 1, [{ id: 1, x: 0, y: 0 }, { id: 9, x: 9, y: 9 }]));
    buf.push(snap(2000, 2, [{ id: 1, x: 10, y: 0 }]));
    const out = buf.sampleAt(1500);
    expect(out.departed).toContain(9);
    // departed agent is pinned at its last-known position
    expect(out.positions.get(9)).toEqual({ x: 9, y: 9, alphaRaw: 1 });
  });
});
```

- [ ] **Step 2: Run fail**

Run: `cd frontend && npx vitest run src/render/interpBuffer.test.ts`

Expected: FAIL.

- [ ] **Step 3: Implement**

Create `frontend/src/render/interpBuffer.ts`:

```ts
// Client-side interpolation buffer.
//
// We keep the last 2 server-pushed snapshots. The canvas renders at
// `renderTime = serverTimeNow - INTERP_DELAY_MS`, which is intentionally
// in the past — this guarantees that for most of the time, renderTime
// falls BETWEEN two known snapshots, so we're always interpolating
// between measured truths instead of extrapolating past the last one.
//
// Per-agent output:
//   positions:     Map<id, {x, y, alphaRaw}> — raw lerp fraction in [0,1]
//   newlyPresent:  ids appearing in the newer snap but not the older
//   departed:      ids present in the older but not newer; drawn at last-known
//
// Why not 3+ snapshots: bandwidth and state are minimal at 1 Hz tick;
// a second's worth of memory is one full snapshot. Two is enough to
// bracket renderTime in steady state.

export interface AgentSample {
  id: number;
  x: number;
  y: number;
}

export interface Snap {
  serverTimeMs: number;
  tick: number;
  agents: AgentSample[];
}

export interface SampleResult {
  positions: Map<number, { x: number; y: number; alphaRaw: number }>;
  newlyPresent: number[];
  departed: number[];
  /** The newer snap's tick (monotonic, suitable as a React key). */
  tick: number;
}

const BUF_SIZE = 2;

export class InterpBuffer {
  private buf: Snap[] = [];

  push(s: Snap): void {
    this.buf.push(s);
    if (this.buf.length > BUF_SIZE) this.buf.shift();
  }

  sampleAt(renderTimeMs: number): SampleResult {
    if (this.buf.length === 0) {
      return { positions: new Map(), newlyPresent: [], departed: [], tick: -1 };
    }
    if (this.buf.length === 1) {
      const only = this.buf[0];
      const positions = new Map<number, { x: number; y: number; alphaRaw: number }>();
      for (const a of only.agents) positions.set(a.id, { x: a.x, y: a.y, alphaRaw: 1 });
      return { positions, newlyPresent: [], departed: [], tick: only.tick };
    }
    const [older, newer] = this.buf;
    const span = newer.serverTimeMs - older.serverTimeMs;
    const raw = span > 0 ? (renderTimeMs - older.serverTimeMs) / span : 1;
    const t = Math.max(0, Math.min(1, raw));

    const olderById = new Map<number, AgentSample>();
    for (const a of older.agents) olderById.set(a.id, a);
    const newerById = new Map<number, AgentSample>();
    for (const a of newer.agents) newerById.set(a.id, a);

    const positions = new Map<number, { x: number; y: number; alphaRaw: number }>();
    const newlyPresent: number[] = [];
    const departed: number[] = [];

    for (const [id, nSamp] of newerById) {
      const o = olderById.get(id);
      if (o) {
        positions.set(id, {
          x: o.x + (nSamp.x - o.x) * t,
          y: o.y + (nSamp.y - o.y) * t,
          alphaRaw: t,
        });
      } else {
        newlyPresent.push(id);
        positions.set(id, { x: nSamp.x, y: nSamp.y, alphaRaw: 1 });
      }
    }
    for (const [id, o] of olderById) {
      if (!newerById.has(id)) {
        departed.push(id);
        // Pin at last-known; lifecycle fade handles the visual exit.
        positions.set(id, { x: o.x, y: o.y, alphaRaw: 1 });
      }
    }

    return { positions, newlyPresent, departed, tick: newer.tick };
  }
}
```

- [ ] **Step 4: Run pass**

Run: `cd frontend && npx vitest run src/render/interpBuffer.test.ts`

Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/render/interpBuffer.ts frontend/src/render/interpBuffer.test.ts
git commit -m "feat(render): InterpBuffer 2-snap ring with time-based sampling"
```

---

### Task 11: Frontend — lifecycle fade state

**Files:**
- Create: `frontend/src/render/lifecycleFade.ts`
- Test: `frontend/src/render/lifecycleFade.test.ts` (new)

- [ ] **Step 1: Write the failing test**

```ts
import { describe, it, expect } from 'vitest';
import { LifecycleFade, FADE_MS } from './lifecycleFade';

describe('LifecycleFade', () => {
  it('new id starts at alpha 0 and eases in to 1 over FADE_MS', () => {
    const f = new LifecycleFade();
    f.update({ present: new Set([1]), now: 1000 });
    expect(f.alphaFor(1, 1000)).toBeCloseTo(0, 3);
    expect(f.alphaFor(1, 1000 + FADE_MS / 2)).toBeGreaterThan(0.5);
    expect(f.alphaFor(1, 1000 + FADE_MS)).toBeCloseTo(1, 3);
    expect(f.alphaFor(1, 1000 + FADE_MS + 500)).toBe(1);
  });

  it('departed id fades from 1 to 0 and then reports undefined', () => {
    const f = new LifecycleFade();
    f.update({ present: new Set([1]), now: 0 });
    f.update({ present: new Set([1]), now: FADE_MS + 100 });
    expect(f.alphaFor(1, FADE_MS + 100)).toBe(1);
    f.update({ present: new Set<number>(), now: FADE_MS + 100 });
    expect(f.alphaFor(1, FADE_MS + 100)).toBeCloseTo(1, 3);
    expect(f.alphaFor(1, FADE_MS + 100 + FADE_MS / 2)).toBeLessThan(0.5);
    expect(f.alphaFor(1, FADE_MS + 100 + FADE_MS)).toBeCloseTo(0, 3);
    // After fade-out completes and we've pruned, the id is gone.
    f.update({ present: new Set<number>(), now: FADE_MS + 100 + FADE_MS + 1 });
    expect(f.has(1)).toBe(false);
  });

  it('lingering ids (still-present) return 1', () => {
    const f = new LifecycleFade();
    f.update({ present: new Set([1]), now: 0 });
    f.update({ present: new Set([1]), now: FADE_MS + 1000 });
    expect(f.alphaFor(1, FADE_MS + 1000)).toBe(1);
  });
});
```

- [ ] **Step 2: Run fail**

Run: `cd frontend && npx vitest run src/render/lifecycleFade.test.ts`

Expected: FAIL.

- [ ] **Step 3: Implement**

Create `frontend/src/render/lifecycleFade.ts`:

```ts
// Per-agent lifecycle fade state.
//
// Why we need it:
//   Backend mutates agent lists. A new spawn pops into view; a death
//   + cleanup vanishes. Today both are instant: a full-opacity pawn
//   appears or disappears in one frame, which reads as "jump / glitch"
//   even at 60 fps. A 250 ms cubic fade bridges the cut.
//
// Model:
//   state: 'in' | 'alive' | 'out'
//   in:    alpha = easeOutCubic((now - startedAt) / FADE_MS), until ≥1
//   alive: alpha = 1
//   out:   alpha = 1 - easeOutCubic((now - startedAt) / FADE_MS), until ≤0
//          then pruned.

import { easeOutCubic } from './ease';

export const FADE_MS = 250;

type Entry = { state: 'in' | 'alive' | 'out'; startedAt: number };

export class LifecycleFade {
  private map = new Map<number, Entry>();

  has(id: number): boolean {
    return this.map.has(id);
  }

  update({ present, now }: { present: Set<number>; now: number }): void {
    // Transition in / confirm alive
    for (const id of present) {
      const e = this.map.get(id);
      if (!e) {
        this.map.set(id, { state: 'in', startedAt: now });
      } else if (e.state === 'in' && now - e.startedAt >= FADE_MS) {
        this.map.set(id, { state: 'alive', startedAt: now });
      } else if (e.state === 'out') {
        // Reappeared before fade-out completed — snap back to alive.
        this.map.set(id, { state: 'alive', startedAt: now });
      }
    }
    // Transition out / prune completed
    for (const [id, e] of this.map) {
      if (!present.has(id)) {
        if (e.state !== 'out') {
          this.map.set(id, { state: 'out', startedAt: now });
        } else if (now - e.startedAt > FADE_MS) {
          this.map.delete(id);
        }
      }
    }
  }

  alphaFor(id: number, now: number): number {
    const e = this.map.get(id);
    if (!e) return 0;
    const dt = now - e.startedAt;
    if (e.state === 'alive') return 1;
    if (e.state === 'in') return easeOutCubic(dt / FADE_MS);
    // state === 'out'
    return 1 - easeOutCubic(Math.min(1, dt / FADE_MS));
  }
}
```

- [ ] **Step 4: Run pass**

Run: `cd frontend && npx vitest run src/render/lifecycleFade.test.ts`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/render/lifecycleFade.ts frontend/src/render/lifecycleFade.test.ts
git commit -m "feat(render): LifecycleFade 250ms cubic in/out for agent lifecycle"
```

---

### Task 12: Frontend — types + query hook for stream

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/api/queries.ts`

- [ ] **Step 1: Extend the type**

Find the `SimulationSummary` (or whatever the poll-response type is named) in `frontend/src/api/types.ts`. Add the two new fields:

```ts
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
  phase: 'day' | 'dusk' | 'night' | 'dawn';
  server_time_ms: number;
  tick_ms: number;
}
```

(Preserve whatever existing fields there are; only add the last two.)

- [ ] **Step 2: Run `tsc` to ensure nothing else relies on the old shape**

Run: `cd frontend && npx tsc --noEmit`

Expected: zero errors. The new fields are additive; call sites that don't consume them stay valid.

- [ ] **Step 3: Add `useWorldStream` hook that returns observed status + latest payload**

Append to `frontend/src/api/queries.ts`:

```ts
import { useEffect, useRef, useState } from 'react';
import { connectWorldStream, type StreamStatus } from './stream';
import type { WorldStateResponse } from './types';

/** Subscribe to the SSE stream. Returns latest snapshot + connection status.
 *  When status flips to 'fallback', the caller should switch back to the
 *  500 ms poll — useWorldState() continues to work regardless. */
export function useWorldStream() {
  const [snapshot, setSnapshot] = useState<WorldStateResponse | null>(null);
  const [status, setStatus] = useState<StreamStatus>('connecting');
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    const conn = connectWorldStream<WorldStateResponse>({
      url: '/api/v1/world/stream',
      onMessage: (m) => {
        if (mounted.current) setSnapshot(m);
      },
      onStatus: (s) => {
        if (mounted.current) setStatus(s);
      },
    });
    return () => {
      mounted.current = false;
      conn.close();
    };
  }, []);

  return { snapshot, status };
}
```

- [ ] **Step 4: Run `tsc` + vitest suite**

```
cd frontend && npx tsc --noEmit
cd frontend && npm test
```

Expected: tsc exit 0. Vitest suite stays green (no regressions).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/api/queries.ts
git commit -m "feat(api): WorldState type adds server_time_ms/tick_ms; useWorldStream hook"
```

---

### Task 13: Frontend — widen snap guard + ease-out + consume `InterpBuffer`

**Files:**
- Modify: `frontend/src/render/Canvas2DRenderer.ts:149-253,486-495`
- Modify: `frontend/src/render/Canvas2DRenderer.test.ts` (extend snap-guard test)

Why bundle these three: they all edit the same per-agent body-position code path. Splitting them would mean three consecutive commits touching the same 15 lines, with each intermediate state not matching any coherent product behavior. The test additions are the granularity; the code is one edit.

- [ ] **Step 1: Extend the snap-guard test**

First, read the existing test file to understand the harness already in use. The file constructs `Canvas2DRenderer` instances, mounts them to a JSDOM-provided host, and calls `drawFrame()` with hand-rolled `FrameSnapshot` objects. Any new test reuses that harness.

Append to `frontend/src/render/Canvas2DRenderer.test.ts`:

```ts
import { InterpBuffer } from './interpBuffer';

describe('snap-guard threshold (widened from 2 to 8)', () => {
  function makeSnap(tick: number, serverTimeMs: number, agents: Array<{ id: number; x: number; y: number }>) {
    return { tick, serverTimeMs, agents };
  }

  it('lerps for dx²+dy² ≤ 8 (e.g. a 2-tile straight step → d²=4)', () => {
    const r = new Canvas2DRenderer();
    const host = document.createElement('div');
    r.mount(host);
    // Feed two snaps 1 s apart: agent 1 moves from (0,0) to (2,0). d² = 4.
    r.ingestSnapshot(makeSnap(1, 1000, [{ id: 1, x: 0, y: 0 }]));
    r.ingestSnapshot(makeSnap(2, 2000, [{ id: 1, x: 2, y: 0 }]));
    // Render at t = 1500 (halfway). Body should be near x ≈ 2 * easeOutCubic(0.5) ≈ 2 * 0.875 = 1.75.
    const frameSnap = {
      width: 4, height: 4, tiles: [], agents: [{ id: 1, x: 2, y: 0, alive: true, colony_id: null, state: 'idle', cargo: 0, hunger: 50, energy: 50, social: 50, health: 100, age: 0, name: 't', rogue: false, loner: false, decision_reason: null }],
      colonies: [], tilePx: 32, cameraX: 0, cameraY: 0, selectedAgentId: null, selectedTile: null,
      reducedMotion: false, currentTick: 2, serverNowMs: 2000, phase: 'day' as const,
    };
    // Stub performance.now() via vi.spyOn to return a specific renderTime.
    vi.spyOn(performance, 'now').mockReturnValue(1500 + 100 /* INTERP_DELAY_MS */);
    r.drawFrame(frameSnap);
    // Read the pixel where the body should be — use a proxy: the
    // renderer's last rendered body position can be exposed via a
    // test-only getter, OR we check the canvas with getImageData.
    // Pick whichever matches the existing test style.
    vi.restoreAllMocks();
  });

  it('snaps for dx²+dy² > 8 (e.g. a 3-tile jump → d²=9)', () => {
    const r = new Canvas2DRenderer();
    const host = document.createElement('div');
    r.mount(host);
    r.ingestSnapshot(makeSnap(1, 1000, [{ id: 1, x: 0, y: 0 }]));
    r.ingestSnapshot(makeSnap(2, 2000, [{ id: 1, x: 3, y: 0 }]));
    // d² = 9 > 8. At t = 1500 (halfway), body should be at target (x=3), not lerped.
    // Assertion follows the same pattern as the first test; body === a.x.
  });
});
```

Note: the existing test harness for `Canvas2DRenderer` (around line 397 of the current file) already shows how to stub `performance.now`, construct `FrameSnapshot`s, and assert about body positions. Reuse those exact helpers — do NOT re-invent. If the assertion style is `getImageData` on the canvas, follow that; if it's a test-only getter on the renderer, add one such getter rather than copy-pasting `getImageData` logic. The critical thing these tests assert is the *threshold*, not the exact pixel — both values around the boundary (d²=4 lerps, d²=9 snaps) exercise that.

- [ ] **Step 2: Run the test to see the current behavior and confirm threshold needs a change**

Run: `cd frontend && npx vitest run src/render/Canvas2DRenderer.test.ts`

Expected: the new tests you just wrote FAIL if the code still uses `<= 2` — which it does.

- [ ] **Step 3: Edit the renderer**

In `frontend/src/render/Canvas2DRenderer.ts`, change the snap guard from `<= 2` to `<= 8` and wrap `alpha` in `easeOutCubic`.

Add import at the top:

```ts
import { easeOutCubic } from './ease';
```

Find the agent body-position block (currently around line 486-495):

```ts
      const prev = this.prevPositions.get(a.id);
      let bodyX = a.x;
      let bodyY = a.y;
      if (prev && !reducedMotion) {
        const dx = a.x - prev.x;
        const dy = a.y - prev.y;
        if (dx * dx + dy * dy <= 2) {
          bodyX = prev.x + dx * alpha;
          bodyY = prev.y + dy * alpha;
        }
      }
```

Change to:

```ts
      const prev = this.prevPositions.get(a.id);
      let bodyX = a.x;
      let bodyY = a.y;
      if (prev && !reducedMotion) {
        const dx = a.x - prev.x;
        const dy = a.y - prev.y;
        // Widened from 2 → 8: allow up to a 2-tile straight or √8 diagonal
        // step to be interpolated instead of snapped. Justification: with
        // the SSE interpolation buffer, inter-tick render gap can be up
        // to INTERP_DELAY_MS + one tick; a legitimate single-tick step
        // visible as a 2-tile delta is network jitter, not "multi-step".
        if (dx * dx + dy * dy <= 8) {
          const eased = easeOutCubic(alpha);
          bodyX = prev.x + dx * eased;
          bodyY = prev.y + dy * eased;
        }
      }
```

- [ ] **Step 4: Run tests**

Run: `cd frontend && npm test`

Expected: all green including the new snap-guard tests.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/render/Canvas2DRenderer.ts frontend/src/render/Canvas2DRenderer.test.ts
git commit -m "feat(render): widen snap guard to 8 + ease-out cubic on lerp"
```

---

### Task 14: Frontend — wire stream → `InterpBuffer` → renderer + fade + fallback

**Files:**
- Modify: `frontend/src/components/WorldCanvas.tsx:68-205`
- Modify: `frontend/src/render/Canvas2DRenderer.ts:~202-253` (replace EMA block with buffer sample)

This is the integration task — where every earlier piece gets plugged in. Split into small steps.

- [ ] **Step 1: Add the buffer + fade state to `Canvas2DRenderer`**

Edit `frontend/src/render/Canvas2DRenderer.ts`. Replace the private `prevPositions`, `lastSeenPositions`, `lastSeenTick`, `lastTickBoundaryAt`, `pollIntervalMs` fields (lines ~149-153) with:

```ts
  private interpBuffer = new InterpBuffer();
  private fade = new LifecycleFade();
```

Import them at the top:

```ts
import { InterpBuffer } from './interpBuffer';
import { LifecycleFade } from './lifecycleFade';
```

- [ ] **Step 2: Expose `ingestSnapshot(snap)` on `Canvas2DRenderer`**

Add a method:

```ts
  /** Called from WorldCanvas when a new server snapshot arrives (SSE or poll).
   *  The renderer owns the interp buffer so the rAF loop can always find
   *  the latest state without threading state through props. */
  ingestSnapshot(snap: {
    serverTimeMs: number;
    tick: number;
    agents: Array<{ id: number; x: number; y: number }>;
  }): void {
    this.interpBuffer.push(snap);
  }
```

- [ ] **Step 3: Replace the alpha/prevPositions block in `drawFrame` with a buffer sample**

In `drawFrame`, delete the entire tick-advance bookkeeping block (currently lines 210-253, starting with `const now = performance.now();` and ending just before the agent loop) and replace with:

```ts
    const now = performance.now();
    // Render INTERP_DELAY_MS behind the most recent server frame. That
    // means in steady state, renderTime always falls between two known
    // snapshots → we interpolate measured truths, never extrapolate.
    // 100 ms masks typical poll/tick jitter while staying below the
    // ~250 ms motion-to-photon threshold where users start to feel
    // "laggy." Adjustable per visual QA in Task 15.
    const INTERP_DELAY_MS = 100;

    // Convert the snapshot's server clock to a render clock by
    // subtracting the interp delay. If the snapshot didn't carry a
    // server clock (very first frame before any push), fall back to
    // `now - INTERP_DELAY_MS` so the buffer can still produce pinned
    // positions at index 0 / end.
    const sampleTimeMs = snap.serverNowMs != null
      ? snap.serverNowMs - INTERP_DELAY_MS
      : now - INTERP_DELAY_MS;

    const sample = this.interpBuffer.sampleAt(sampleTimeMs);

    // Drive fade state from what the buffer reports as "present right now":
    // any id the buffer returns a position for (including departed-and-pinned)
    // is still on screen this frame.
    const presentIds = new Set<number>();
    for (const id of sample.positions.keys()) presentIds.add(id);
    this.fade.update({ present: presentIds, now });
```

(Keep all the OTHER state — sprites, animStates, resize cache — exactly as is.)

Then in the agent draw loop, replace the per-agent `prev = this.prevPositions.get(a.id)` / snap-guard block with:

```ts
      const p = sample.positions.get(a.id);
      const bodyX = p?.x ?? a.x;
      const bodyY = p?.y ?? a.y;
      const lifecycleAlpha = this.fade.alphaFor(a.id, now);
      // Multiply into the existing alive/traversing alpha below.
```

And in every `ctx.drawImage(...)` call for the pawn body (3 of them: dead, traversing, alive), wrap in `ctx.save()` / `ctx.globalAlpha *= lifecycleAlpha` / `ctx.restore()`. Concretely, replace lines 559-571 with:

```ts
        ctx.save();
        if (!a.alive) ctx.globalAlpha = 0.35 * lifecycleAlpha;
        else if (traversing) ctx.globalAlpha = 0.75 * lifecycleAlpha;
        else ctx.globalAlpha = lifecycleAlpha;
        ctx.drawImage(sheet, srcX, srcY, srcW, srcH, pawnX, pawnY, pawnW, pawnH);
        ctx.restore();
```

Keep `animStates` frame-cycling untouched (animation is not a lifecycle concern — a pawn fading in still head-bobs normally).

- [ ] **Step 4: Remove now-dead code**

Delete the now-unused `prevPositions` / `lastSeenPositions` / `lastSeenTick` / `lastTickBoundaryAt` / `pollIntervalMs` fields AND their references in `dispose()`. The `_drawStateIcon`, sprite path, and anim-advance paths don't depend on them — verify by running `npx tsc --noEmit` and fixing each referenced-but-removed symbol (there should be few; all live in the block you just replaced).

- [ ] **Step 5: Wire `WorldCanvas` to feed both the stream AND the poll into the renderer**

Edit `frontend/src/components/WorldCanvas.tsx`. Add the stream hook:

```tsx
import { useWorldStream } from '../api/queries';
```

After the existing `sim = useSimulation()` line, add:

```tsx
const { snapshot: streamSnap, status: streamStatus } = useWorldStream();
```

In the `useEffect` that builds `snapRef.current` (line 115), change the agents/tick source to prefer stream when available:

```tsx
useEffect(() => {
  if (!world.data) { snapRef.current = null; return; }
  const effectiveAgents = streamSnap?.agents ?? agents.data ?? [];
  const effectiveSim = streamSnap?.sim ?? sim.data;
  snapRef.current = {
    width: world.data.width,
    height: world.data.height,
    tiles: world.data.tiles,
    agents: effectiveAgents,
    colonies: streamSnap?.colonies ?? colonies.data ?? [],
    tilePx,
    cameraX,
    cameraY,
    selectedAgentId,
    selectedTile,
    reducedMotion: isReducedMotion(),
    currentTick: effectiveSim?.tick ?? 0,
    serverNowMs: effectiveSim?.server_time_ms,
    phase: effectiveSim?.phase,
  };
  // Push the tick boundary into the renderer's interp buffer.
  if (rendererRef.current && effectiveSim?.server_time_ms != null) {
    rendererRef.current.ingestSnapshot({
      serverTimeMs: effectiveSim.server_time_ms,
      tick: effectiveSim.tick,
      agents: effectiveAgents.map(a => ({ id: a.id, x: a.x, y: a.y })),
    });
  }
}, [
  world.data, agents.data, colonies.data, tilePx, cameraX, cameraY,
  selectedAgentId, selectedTile, sim.data?.tick, sim.data?.phase,
  streamSnap,
]);
```

Add `serverNowMs?: number` to the `FrameSnapshot` type in wherever it's defined (`frontend/src/render/rendererTypes.ts` or the top of `Canvas2DRenderer.ts`).

- [ ] **Step 6: Fallback — if stream status is 'fallback', the poll hook already runs unconditionally, so nothing to do**

Verify by reading `frontend/src/api/queries.ts`: `useWorldState()` keeps polling at 500 ms whenever `running === true`. That means:
- stream connected: renderer sees new snapshots every tick via SSE (1 Hz at speed 1.0).
- stream 'reconnecting': no new snapshots until SSE recovers. Poll fills the gap at 500 ms.
- stream 'fallback': never recovers. Poll remains the source of truth.

Tasks 1-13 guarantee the buffer produces smooth motion in either case — the buffer only cares about `serverTimeMs`, not which transport delivered it.

- [ ] **Step 7: Tests + tsc**

```
cd frontend && npx tsc --noEmit
cd frontend && npm test
```

Expected: tsc clean. Vitest green. (The unit tests for InterpBuffer, LifecycleFade, snap-guard, ease, and stream each cover their module; the integration here is not unit-tested directly — Task 15 covers it via headless capture.)

- [ ] **Step 8: Commit**

```bash
git add frontend/src/render/Canvas2DRenderer.ts frontend/src/components/WorldCanvas.tsx frontend/src/render/rendererTypes.ts
git commit -m "feat(render,canvas): consume InterpBuffer + LifecycleFade; SSE-preferred snapshot path"
```

---

### Task 15: Integration — visual QA via headless Chromium

**Files:**
- Modify: `scripts/visual_capture.py` (extend to report per-frame agent deltas)
- Add: `scripts/analyze_frames.py` (new — computes teleport/flicker metrics from the capture)

Why: the per-module unit tests cover math. Visual correctness is a separate claim and per CLAUDE.md §Validation workflow must be demonstrated against a reproducer.

- [ ] **Step 1: Extend `scripts/visual_capture.py` to also dump per-frame JSON**

Add (next to the screenshot call) a `page.evaluate()` that reads the raw `GET /api/v1/world/state` response at each frame, attaching it to the PNG filename so we can correlate.

```python
# Inside the frame loop, right after the canvas screenshot:
state_json = await page.evaluate("""
  () => fetch('/api/v1/world/state').then(r => r.json())
""")
(OUT_DIR / f'frame_{i:03d}_t{int(elapsed_ms):05d}ms.json').write_text(
    __import__('json').dumps({
        'tick': state_json['sim']['tick'],
        'server_time_ms': state_json['sim'].get('server_time_ms'),
        'agents': [
            {'id': a['id'], 'x': a['x'], 'y': a['y'], 'alive': a['alive']}
            for a in state_json['agents']
        ],
    })
)
```

- [ ] **Step 2: Write `scripts/analyze_frames.py`**

```python
"""Post-process the JSON dumps from visual_capture.py:
  * detect any per-agent dx²+dy² > 8 between consecutive frames
    (i.e. a visual teleport even after Tier 2's widening)
  * detect any flicker (id present → absent → present within 2 s)
  * print the server-time spacing to confirm the stream cadence
"""
import json
import pathlib
import sys

OUT_DIR = pathlib.Path('/tmp/vis_capture')

def main():
    frames = sorted(OUT_DIR.glob('frame_*.json'))
    prev_agents = {}
    last_seen = {}  # id → last frame index
    teleports = []
    flickers = []
    for i, f in enumerate(frames):
        data = json.loads(f.read_text())
        curr = {a['id']: (a['x'], a['y']) for a in data['agents']}
        for aid, (x, y) in curr.items():
            if aid in prev_agents:
                px, py = prev_agents[aid]
                d2 = (x - px) ** 2 + (y - py) ** 2
                if d2 > 8:
                    teleports.append((i, aid, d2, (px, py), (x, y)))
            if aid in last_seen and i - last_seen[aid] > 1:
                flickers.append((i, aid, last_seen[aid], i - last_seen[aid]))
            last_seen[aid] = i
        prev_agents = curr
    print(f'frames: {len(frames)}')
    print(f'teleports (dx²+dy² > 8): {len(teleports)}')
    for t in teleports[:5]: print(' ', t)
    print(f'flickers (id missing ≥ 1 frame): {len(flickers)}')
    for fl in flickers[:5]: print(' ', fl)
    sys.exit(0 if not teleports and not flickers else 1)

if __name__ == '__main__':
    main()
```

- [ ] **Step 3: Full verification run**

```bash
docker compose restart flask
sleep 8
/tmp/pw-venv/bin/python scripts/visual_capture.py
python3 scripts/analyze_frames.py
```

Expected: `teleports: 0`, `flickers: 0`, exit code 0. Also eyeball 5 spaced frames and confirm pawns don't pop.

- [ ] **Step 4: Commit**

```bash
git add scripts/visual_capture.py scripts/analyze_frames.py
git commit -m "test(scripts): visual capture emits per-frame JSON + teleport analyzer"
```

---

### Task 16: Full-suite verification, tag, push decision

**Files:** none (ops only)

- [ ] **Step 1: Run all backend + frontend suites**

```bash
docker compose exec -T flask pytest
cd /mnt/c/Users/mauro/Dev/Tunnels_Demo/frontend && npm test
cd /mnt/c/Users/mauro/Dev/Tunnels_Demo/frontend && npx tsc --noEmit
```

Expected numbers: backend ≥ 258 green (252 baseline + Tasks 1, 2, 4, 5, 6, 7 add tests); frontend ≥ 68 green (58 baseline + Tasks 8, 9, 10, 11 add tests + Task 13 extends existing).

- [ ] **Step 2: Repro scripts clean**

```bash
python3 scripts/repro_put_race.py   # should show ticks continuing after the mid-run PUT
CAPTURE_SEC=60 python3 scripts/repro_teleport.py  # snap-trips should stay 0
python3 scripts/analyze_frames.py    # from Task 15; exit 0
```

- [ ] **Step 3: Manual UI walkthrough**

Load `http://localhost`. Generate sim. Watch 30 s at default speed. Criteria:
1. Agents slide smoothly tile-to-tile (no per-tile judder).
2. Arrival is ease-out (fast approach → gentle settle).
3. Cargo variant swap: no pop — body alpha stays 1 through the swap.
4. Regenerate mid-run via the sidebar button: old pawns fade out 250 ms while new ones fade in; tick counter resumes without a stuck "paused" state.
5. Network-throttle test: DevTools → Network → Slow 3G for 10 s. Stream status indicator (if surfaced) flips to reconnecting; agents freeze at last-known pos but don't teleport when traffic resumes.

If any fails, file as a follow-up bug and do NOT tag — the fix lands first.

- [ ] **Step 4: Tag the netcode round**

```bash
git tag netcode-smoothness-round1
```

- [ ] **Step 5: Decision: push or stage**

Two unpushed blocks now sit on `master`: (a) agent-shine-round3 (27 commits from prior session) and (b) netcode-smoothness (this plan's commits). User decides whether to:
- Push both blocks at once (`git push origin master && git push origin agent-shine-round3 netcode-smoothness-round1`), or
- Open a PR for netcode-smoothness only off a `netcode-smoothness` branch to isolate review.

Default assumption for demo week: push master. PR review optional.

- [ ] **Step 6: Update memory**

Update `/home/mauro/.claude/projects/-mnt-c-Users-mauro-Dev-Tunnels-Demo/memory/project_tunnels_agent_shine_progress.md` OR create a new memory `project_tunnels_netcode_smoothness.md` with the final tick/test counts and tag placement.

---

## Spec ↔ task coverage check

| Spec bullet | Task(s) |
|---|---|
| Fix PUT-while-running FK race | 1, 2, 3 |
| `server_time_ms` + `tick_ms` on wire | 4 |
| In-process pub-sub | 5, 6 |
| SSE endpoint `/api/v1/world/stream` | 7 |
| Client EventSource + reconnect + fallback | 8 |
| Ease-out cubic | 9, 13 |
| 2-snapshot interp buffer with interp delay | 10, 14 |
| Lifecycle fade in/out | 11, 14 |
| Snap-guard widen from 2 to 8 | 13 |
| Types for new wire fields | 12 |
| Integration + visual QA | 15 |
| Verification + tag + push | 16 |

No gaps.

---

## Risks + mitigations

| Risk | Mitigation |
|---|---|
| Werkzeug dev server doesn't flush SSE on demand | Test in Task 7 asserts streaming works against the live container. If broken: downgrade to gunicorn in docker-compose or run `flask run --with-threads` explicitly. |
| `stream_with_context` holds DB session open too long | Our generator does NOT touch DB — only reads from `broadcaster` queue. Safe. |
| React StrictMode double-mount of WorldCanvas opens 2 EventSources | `connectWorldStream` returns a `close()` which useEffect cleanup calls; acceptable to briefly have 2 connections in dev. Not a prod concern. |
| `INTERP_DELAY_MS = 100` feels laggy | Adjustable constant; visual QA in Task 15 tunes it. Acceptable range 50-200 ms. |
| Stream floods frontend when backend speeds up | `broadcaster.publish` is non-blocking and per-subscriber queue is bounded at 8. If a client stalls, newest-N frames drop; client recovers on next push. |
