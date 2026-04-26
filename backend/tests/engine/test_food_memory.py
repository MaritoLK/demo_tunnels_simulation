"""Per-agent food memory: explore biases toward last successful forage
tiles instead of random walking.

Pre-fix the all-needs-ok tail action was a coin-flip neighbour pick —
agents looked aimless. Memory turns that into a patrol toward known
caches, which reads as deliberate scouting. Capped to FOOD_MEMORY_MAX
so a long run doesn't grow the slot unbounded; depleted tiles are
pruned at the consumer (explore) so we don't accumulate phantom
anchors.
"""
import random

from app.engine import actions, config, needs
from app.engine.agent import Agent
from app.engine.world import Tile, World


def _grass(width=8, height=8):
    w = World(width, height)
    w.tiles = [
        [Tile(x, y, 'grass') for x in range(width)]
        for y in range(height)
    ]
    return w


def _food_at(world, x, y, amount):
    t = world.tiles[y][x]
    t.resource_type = 'food'
    t.resource_amount = amount
    return t


class _FixedRng:
    def __init__(self, randint_value=10):
        import random as _r
        self._value = randint_value
        self._fallback = _r.Random(0)

    def randint(self, lo, hi):
        return self._value

    def choice(self, seq):
        return self._fallback.choice(seq)

    def random(self):
        return self._fallback.random()


def test_successful_forage_appends_tile_to_memory():
    a = Agent(name='A', x=2, y=2, agent_id=1, colony_id=1)
    a.hunger = 50.0
    w = _grass()
    _food_at(w, 2, 2, 10.0)
    actions.forage(a, w, rng=_FixedRng(13))  # mid-band → 2 yield > 0
    assert a.food_memory == [(2, 2)]


def test_zero_yield_forage_does_not_record_in_memory():
    # Crit-fail or empty-tile / full-pouch yields 0 — that tile didn't
    # earn a slot in memory. Pre-fix this would have stamped the tile
    # anyway and the patrol AI would chase a worthless lead.
    a = Agent(name='A', x=2, y=2, agent_id=1, colony_id=1)
    a.hunger = 50.0
    w = _grass()
    _food_at(w, 2, 2, 10.0)
    actions.forage(a, w, rng=_FixedRng(1))  # crit fail → 0 yield
    assert a.food_memory == []


def test_memory_capped_at_food_memory_max():
    a = Agent(name='A', x=2, y=2, agent_id=1, colony_id=1)
    a.hunger = 50.0
    w = _grass()
    # Walk-and-forage in a loop with FOOD_MEMORY_MAX + 2 distinct tiles
    # to guarantee multiple distinct entries; assert the slot trimmed
    # the oldest, kept the most recent FOOD_MEMORY_MAX.
    distinct = config.FOOD_MEMORY_MAX + 2
    for i in range(distinct):
        _food_at(w, i, 0, 10.0)
        a.x, a.y = i, 0
        # Reset cargo each iteration so the pouch never caps and every
        # forage actually yields. Without this, cargo fills and later
        # iterations roll a 0-yield forage that skips the memory append
        # — masking the cap behaviour we're trying to test.
        a.cargo_food = 0.0
        actions.forage(a, w, rng=_FixedRng(13))
    assert len(a.food_memory) == config.FOOD_MEMORY_MAX
    expected = [(i, 0) for i in range(distinct - config.FOOD_MEMORY_MAX, distinct)]
    assert a.food_memory == expected


def test_explore_steps_toward_remembered_food_when_memory_present():
    a = Agent(name='A', x=0, y=0, agent_id=1, colony_id=1)
    w = _grass()
    a.food_memory = [(5, 0)]
    _food_at(w, 5, 0, 10.0)  # still has food, so memory not pruned
    ev = actions.explore(a, w, rng=_FixedRng(13))
    assert ev['type'] == 'moved'
    # Should step right (toward (5,0)). Manhattan distance dropped.
    assert abs(a.x - 5) + abs(a.y - 0) < 5
    assert 'patrolled toward known food' in ev['description']


def test_explore_falls_back_to_random_walk_when_memory_empty():
    a = Agent(name='A', x=4, y=4, agent_id=1, colony_id=1)
    w = _grass()
    assert a.food_memory == []
    ev = actions.explore(a, w, rng=_FixedRng(13))
    # No "patrolled toward" text — fell to random walk.
    assert 'patrolled toward known food' not in ev['description']


def test_explore_prunes_depleted_memory_entries():
    # Agent remembers a tile that's been emptied since. Pruning
    # happens at explore-time so the agent doesn't loop back to a
    # ghost cache.
    a = Agent(name='A', x=0, y=0, agent_id=1, colony_id=1)
    w = _grass()
    a.food_memory = [(5, 0), (7, 0)]
    _food_at(w, 5, 0, 0.0)  # depleted
    _food_at(w, 7, 0, 8.0)  # still good
    actions.explore(a, w, rng=_FixedRng(13))
    # (5,0) pruned, (7,0) kept. Agent should be moving toward (7,0).
    assert a.food_memory == [(7, 0)]
