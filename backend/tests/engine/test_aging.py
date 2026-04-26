"""Natural death by old age.

`agent.age` already increments per tick. Past `MAX_AGE_TICKS` the agent
dies a natural death (event type 'died' with cause='old age', distinct
from cause='starvation'). Caught in the pre-decay block of tick_agent
so age-out and starvation deaths don't fight each other on the same
tick.
"""
import random

from app.engine import actions, config
from app.engine.agent import Agent, tick_agent
from app.engine.colony import EngineColony
from app.engine.world import Tile, World


def _grass():
    w = World(10, 10)
    w.tiles = [[Tile(x, y, 'grass') for x in range(10)] for y in range(10)]
    return w


def _colony():
    return EngineColony(id=1, name='Red', color='#e74c3c',
                        camp_x=0, camp_y=0, food_stock=20)


def test_agent_dies_at_max_age():
    a = Agent('A', 5, 5, agent_id=1, colony_id=1)
    a.age = config.MAX_AGE_TICKS
    events = tick_agent(a, _grass(), [a], {1: _colony()},
                        phase='day', rng=random.Random(0))
    assert not a.alive
    deaths = [e for e in events if e['type'] == 'died']
    assert deaths, f'no death event in {events}'
    assert deaths[0]['data']['cause'] == 'old age'


def test_agent_below_max_age_does_not_die_of_age():
    a = Agent('A', 5, 5, agent_id=1, colony_id=1)
    a.age = config.MAX_AGE_TICKS - 1
    events = tick_agent(a, _grass(), [a], {1: _colony()},
                        phase='day', rng=random.Random(0))
    assert a.alive, f'agent died below MAX_AGE: events={events}'
    assert not any(e['type'] == 'died' for e in events)


def test_starvation_death_tagged_distinctly_from_old_age():
    # Force a starvation death so we can verify the cause field
    # discriminates between the two paths.
    a = Agent('A', 5, 5, agent_id=1, colony_id=1)
    a.health = 0.5
    a.hunger = 0.0  # decay → -2 hp → die
    events = tick_agent(a, _grass(), [a], {1: _colony()},
                        phase='day', rng=random.Random(0))
    deaths = [e for e in events if e['type'] == 'died']
    assert deaths
    assert deaths[0]['data']['cause'] == 'starvation', (
        f"expected cause='starvation', got {deaths[0]['data']!r}"
    )


def test_aged_out_agent_emits_only_one_death():
    # The pre-decay aging check fires before need decay. An over-age
    # agent should produce exactly one death event, not also a
    # starvation death even if their hunger was zero.
    a = Agent('A', 5, 5, agent_id=1, colony_id=1)
    a.age = config.MAX_AGE_TICKS + 5
    a.hunger = 0.0
    a.health = 0.5
    events = tick_agent(a, _grass(), [a], {1: _colony()},
                        phase='day', rng=random.Random(0))
    deaths = [e for e in events if e['type'] == 'died']
    assert len(deaths) == 1, f'expected 1 death event, got {len(deaths)}'
    assert deaths[0]['data']['cause'] == 'old age'


def test_max_age_threshold_is_finite_and_reachable():
    # Sanity guard: 0 < MAX_AGE_TICKS < some absurdly-large number.
    # If a future tweak set this to None or a very large value, the
    # mechanic would silently die.
    assert config.MAX_AGE_TICKS > 0
    assert config.MAX_AGE_TICKS < 100_000  # ~13 real-world hours at 10ms ticks
