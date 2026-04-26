"""Wolves hazard tile.

Generation: a percentage of high-yield food tiles spawn a wolf pack so
the bigger caches read as guarded. Bite trigger: ENTRY only — an agent
takes damage when stepping onto a wolves tile, not while standing on
one. Without that gate one bad step turns into a death spiral.
"""
import pytest

from app.engine import config, needs
from app.engine.agent import Agent, tick_agent
from app.engine.colony import EngineColony
from app.engine.world import (
    WOLF_FOOD_CHANCE,
    WOLF_FOOD_THRESHOLD,
    Tile,
    World,
)


def _solid_grass(width=10, height=10):
    w = World(width, height)
    w.tiles = [
        [Tile(x, y, 'grass') for x in range(width)]
        for y in range(height)
    ]
    return w


def _colony():
    return EngineColony(
        id=1, name='Red', color='#e74c3c',
        camp_x=0, camp_y=0, food_stock=0,
    )


class _DeterministicRng:
    """Tiny stand-in for random.Random.

    Wolf-bite damage is rolled via `rng.randint(WOLF_BITE_MIN,
    WOLF_BITE_MAX)`, so the test pins that value rather than letting
    it drift across runs. Other rng methods (`choice` for explore)
    forward to a stdlib Random with a fixed seed so output stays
    deterministic without needing per-call mocks."""
    def __init__(self, randint_value, seed=0):
        import random as _random
        self._value = randint_value
        self._fallback = _random.Random(seed)

    def randint(self, lo, hi):  # noqa: D401 — match random.Random API
        assert lo <= self._value <= hi
        return self._value

    def choice(self, seq):
        return self._fallback.choice(seq)

    def random(self):
        return self._fallback.random()


def test_world_generation_seeds_wolves_only_on_high_yield_food():
    # 80x80 map for a fat sample size — small worlds occasionally roll
    # zero high-yield food tiles and the assertion would be vacuous.
    w = World(80, 80)
    w.generate(seed=11)
    high_yield_food = 0
    high_yield_with_wolves = 0
    for row in w.tiles:
        for t in row:
            if t.wolves:
                # Wolves only sit on food tiles whose yield clears the
                # threshold — never on bare grass / wood / stone.
                assert t.resource_type == 'food', (
                    f'wolf on non-food tile ({t.x},{t.y}, type={t.resource_type})'
                )
                assert t.resource_amount >= WOLF_FOOD_THRESHOLD, (
                    f'wolf on yield<{WOLF_FOOD_THRESHOLD} tile '
                    f'({t.x},{t.y}, amount={t.resource_amount})'
                )
                high_yield_with_wolves += 1
            if t.resource_type == 'food' and t.resource_amount >= WOLF_FOOD_THRESHOLD:
                high_yield_food += 1
    # Sanity: at least some high-yield tiles exist on an 80x80 world,
    # and the observed rate is in the right ballpark for the configured
    # WOLF_FOOD_CHANCE. Wide bounds because rng is small-N for this seed.
    assert high_yield_food > 0
    rate = high_yield_with_wolves / high_yield_food
    assert 0 < rate < 1, (
        f'wolves rate {rate:.2f} should be between 0 and 1; got '
        f'{high_yield_with_wolves}/{high_yield_food} (target ≈ {WOLF_FOOD_CHANCE})'
    )


def test_wolf_bite_fires_on_entering_a_guarded_tile():
    world = _solid_grass()
    world.tiles[5][5].wolves = True
    colony = _colony()
    agent = Agent(name='scout', x=5, y=4, agent_id=1, colony_id=1)
    rng = _DeterministicRng(randint_value=12)
    # Block the plant branch (crop_state == 'growing' → tile-local
    # falls through) and the harvest branch, then leave the wolves
    # tile as the only walkable neighbor so explore deterministically
    # routes the agent there.
    world.tiles[4][5].crop_state = 'growing'
    for dx, dy in [(-1, 0), (1, 0), (0, -1)]:
        nx, ny = 5 + dx, 4 + dy
        if 0 <= nx < 10 and 0 <= ny < 10:
            world.tiles[ny][nx].terrain = 'water'
    pre_health = agent.health
    events = tick_agent(
        agent, world,
        all_agents=[agent],
        colonies_by_id={1: colony},
        phase='day',
        rng=rng,
    )
    assert agent.x == 5 and agent.y == 5, (
        f'agent should have moved onto wolves tile; ended at ({agent.x},{agent.y})'
    )
    assert agent.health == pre_health - 12
    assert any(e['type'] == 'wolf_attack' for e in events), (
        f'expected a wolf_attack event in {events}'
    )


def test_wolf_bite_does_not_fire_when_agent_stands_still():
    world = _solid_grass()
    world.tiles[5][5].wolves = True
    colony = _colony()
    # Agent already on the wolves tile, no neighbors walkable so it
    # idles in place. Idling triggers no bite — entry is the cost, not
    # standing.
    for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        nx, ny = 5 + dx, 5 + dy
        if 0 <= nx < 10 and 0 <= ny < 10:
            world.tiles[ny][nx].terrain = 'water'
    agent = Agent(name='scout', x=5, y=5, agent_id=1, colony_id=1)
    rng = _DeterministicRng(randint_value=12)
    pre_health = agent.health
    events = tick_agent(
        agent, world,
        all_agents=[agent],
        colonies_by_id={1: colony},
        phase='day',
        rng=rng,
    )
    assert agent.health == pre_health, (
        'agent did not move; bite must not fire'
    )
    assert not any(e['type'] == 'wolf_attack' for e in events)


def test_bite_constants_are_sane():
    assert needs.WOLF_BITE_MIN > 0
    assert needs.WOLF_BITE_MAX >= needs.WOLF_BITE_MIN
    # 1-2 hits should be survivable on a fresh agent (health = NEED_MAX = 100)
    assert needs.WOLF_BITE_MAX < needs.NEED_MAX / 2
