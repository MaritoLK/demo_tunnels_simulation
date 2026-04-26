"""Dawn-meal reproduction ritual.

Trigger: at dawn, if (a) a colony's food_stock >= REPRODUCTION_FOOD_THRESHOLD,
(b) at least one alive non-rogue colony agent is on the camp tile (the
'midwife'), (c) population is below MAX_AGENTS_PER_COLONY, and (d) the
per-colony cooldown REPRODUCTION_COOLDOWN_TICKS has elapsed since the
last birth — then a child agent spawns at the camp tile, food_stock
debits REPRODUCTION_FOOD_COST, and `colony.last_reproduction_tick` is
stamped to the current tick.

The 'both adults at camp simultaneously' alternative was rejected after
the 1500-tick diagnostic: the existing socialise action — which uses
that exact gate — fired only 4 times in 1500 ticks. Coupling birth to
that would mean ~zero births per demo. The dawn-meal ritual ties to
eat_camp's existing rhythm: someone is almost always on the camp tile
during dawn.
"""
from app.engine import config
from app.engine.agent import Agent
from app.engine.colony import EngineColony
from app.engine.simulation import Simulation
from app.engine.world import Tile, World


def _grass(width=20, height=20):
    w = World(width, height)
    w.tiles = [
        [Tile(x, y, 'grass') for x in range(width)]
        for y in range(height)
    ]
    return w


def _colony(food=50, last_repro=None):
    c = EngineColony(
        id=1, name='Red', color='#e74c3c',
        camp_x=10, camp_y=10, food_stock=food,
    )
    c.last_reproduction_tick = last_repro
    return c


def _camped_agent():
    return Agent('A', 10, 10, agent_id=1, colony_id=1)


def test_dawn_with_food_surplus_and_midwife_spawns_child():
    sim = Simulation(_grass(), colonies=[_colony(food=50)])
    sim.agents.append(_camped_agent())
    sim.current_tick = 0  # tick 0 = dawn
    pre = len(sim.agents)
    events = sim.step()
    post = len(sim.agents)
    assert post == pre + 1, (
        f'expected one birth, agent count {pre} → {post}'
    )
    # Birth event fires.
    births = [e for e in events if e['type'] == 'birthed']
    assert births, f'no birth event in {events}'
    assert births[0]['data']['colony_id'] == 1


def test_no_reproduction_below_food_threshold():
    sim = Simulation(_grass(), colonies=[
        _colony(food=config.REPRODUCTION_FOOD_THRESHOLD - 1)
    ])
    sim.agents.append(_camped_agent())
    sim.current_tick = 0  # dawn
    pre = len(sim.agents)
    sim.step()
    assert len(sim.agents) == pre, (
        'reproduction fired despite food below threshold'
    )


def test_no_reproduction_during_cooldown():
    # last_reproduction_tick set to "now-ish" so cooldown hasn't elapsed.
    sim = Simulation(_grass(), colonies=[
        _colony(food=50, last_repro=0)
    ])
    sim.agents.append(_camped_agent())
    sim.current_tick = config.REPRODUCTION_COOLDOWN_TICKS - 1
    # Roll the tick forward without stepping (we only care about
    # the next dawn). Simpler: directly invoke the check at a tick
    # within cooldown but ALSO during dawn phase.
    # Find next dawn tick within cooldown:
    from app.engine import cycle
    next_dawn = ((cycle.PHASES.index('dawn'))
                 * cycle.TICKS_PER_PHASE)
    # Set tick = exactly cooldown - 1 ticks after last_repro_tick=0,
    # and force phase to 'dawn'. The cleanest way: pick a tick in
    # the dawn band that's still inside the cooldown window.
    sim.current_tick = next_dawn  # tick 0, dawn, cooldown not elapsed
    pre = len(sim.agents)
    sim.step()
    assert len(sim.agents) == pre, (
        'reproduction fired during cooldown window'
    )


def test_reproduction_resumes_after_cooldown_elapses():
    sim = Simulation(_grass(), colonies=[
        _colony(food=50, last_repro=0),
    ])
    sim.agents.append(_camped_agent())
    # Skip past the cooldown to the next dawn.
    from app.engine import cycle
    sim.current_tick = config.REPRODUCTION_COOLDOWN_TICKS
    # Roll to a dawn phase tick at or beyond that.
    while cycle.phase_for(sim.current_tick) != 'dawn':
        sim.current_tick += 1
    pre = len(sim.agents)
    sim.step()
    assert len(sim.agents) == pre + 1, (
        f'reproduction did not resume after cooldown: pre={pre}, '
        f'post={len(sim.agents)}'
    )


def test_no_reproduction_at_population_cap():
    sim = Simulation(_grass(), colonies=[_colony(food=50)])
    # Fill colony to cap.
    for i in range(config.MAX_AGENTS_PER_COLONY):
        a = Agent(f'A{i}', 10, 10, agent_id=i + 1, colony_id=1)
        sim.agents.append(a)
    sim.current_tick = 0
    pre = len(sim.agents)
    sim.step()
    assert len(sim.agents) == pre, (
        f'reproduction exceeded cap: pre={pre}, post={len(sim.agents)}, '
        f'cap={config.MAX_AGENTS_PER_COLONY}'
    )


def test_no_reproduction_when_colony_has_no_living_non_rogue_member():
    # No alive non-rogue member → no midwife → no birth. Position
    # doesn't matter — the colony as a whole is the unit, and a
    # collapsed colony shouldn't spontaneously generate offspring.
    sim = Simulation(_grass(), colonies=[_colony(food=50)])
    # Single rogue agent: alive but excluded from midwife pool.
    a = Agent('A', 10, 10, agent_id=1, colony_id=1)
    a.rogue = True
    sim.agents.append(a)
    sim.current_tick = 0
    pre = len(sim.agents)
    sim.step()
    assert len(sim.agents) == pre, (
        'reproduction fired with only a rogue agent — should not'
    )


def test_reproduction_debits_food_stock():
    sim = Simulation(_grass(), colonies=[_colony(food=50)])
    sim.agents.append(_camped_agent())
    sim.current_tick = 0
    pre_stock = sim.colonies[1].food_stock
    sim.step()
    assert sim.colonies[1].food_stock <= pre_stock - config.REPRODUCTION_FOOD_COST, (
        f'food_stock did not debit reproduction cost: '
        f'pre={pre_stock}, post={sim.colonies[1].food_stock}'
    )


def test_reproduction_only_in_dawn_phase():
    # Force tick into 'day' phase. Even with food + midwife + cooldown
    # elapsed, no birth fires outside dawn.
    sim = Simulation(_grass(), colonies=[_colony(food=50)])
    sim.agents.append(_camped_agent())
    from app.engine import cycle
    sim.current_tick = cycle.PHASES.index('day') * cycle.TICKS_PER_PHASE
    pre = len(sim.agents)
    sim.step()
    assert len(sim.agents) == pre, (
        'reproduction fired outside dawn phase'
    )


def test_child_spawns_on_camp_tile_with_full_needs():
    sim = Simulation(_grass(), colonies=[_colony(food=50)])
    sim.agents.append(_camped_agent())
    sim.current_tick = 0
    sim.step()
    # The new agent is the last appended.
    child = sim.agents[-1]
    assert (child.x, child.y) == (10, 10)
    assert child.colony_id == 1
    assert child.age == 0
    assert child.alive
    # Newborn starts well-fed/rested so they don't immediately starve.
    assert child.hunger > 0
    assert child.energy > 0


def test_rogue_agent_does_not_qualify_as_midwife():
    # Rogue is no longer 'in the tribe' — their presence at camp
    # shouldn't trigger reproduction. Only non-rogue colony members
    # count as midwives.
    sim = Simulation(_grass(), colonies=[_colony(food=50)])
    a = _camped_agent()
    a.rogue = True
    sim.agents.append(a)
    sim.current_tick = 0
    pre = len(sim.agents)
    sim.step()
    assert len(sim.agents) == pre, (
        'rogue agent qualified as midwife — should not'
    )
