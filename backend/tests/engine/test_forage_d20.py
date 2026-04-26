"""d20 forage roll: replaces the deterministic FORAGE_TILE_DEPLETION
with a banded yield so the gather action has visible variance + crit
fail / crit success moments without changing long-run pacing."""
from app.engine import actions, needs


class _FixedRng:
    """random.Random shim that emits a fixed value for randint() so each
    test pins exactly which d20 band the forage falls into."""
    def __init__(self, value):
        self._value = value

    def randint(self, lo, hi):
        assert lo <= self._value <= hi, (
            f'fixed-rng value {self._value} outside [{lo},{hi}]'
        )
        return self._value


def test_d20_banding():
    # Each input → expected ceiling. Asserts the lookup table directly
    # so a future tuning pass can see at a glance which rolls map where.
    cases = [
        (1, 0),    # crit fail
        (2, 1), (5, 1),    # low band edges
        (6, 2), (10, 2), (15, 2),    # mid band
        (16, 3), (19, 3),    # good band edges
        (20, 5),    # crit
    ]
    for roll, expected_yield in cases:
        got_roll, got_yield = actions._forage_yield_from_d20(_FixedRng(roll))
        assert got_roll == roll
        assert got_yield == expected_yield, (
            f'd20={roll} expected ceiling {expected_yield}, got {got_yield}'
        )


def _grass_world(width=4, height=4):
    from app.engine.world import Tile, World
    w = World(width, height)
    w.tiles = [
        [Tile(x, y, 'grass') for x in range(width)]
        for y in range(height)
    ]
    return w


def _food_at(world, x, y, amount):
    tile = world.tiles[y][x]
    tile.resource_type = 'food'
    tile.resource_amount = amount
    return tile


def test_forage_event_carries_roll_and_taken():
    from app.engine.agent import Agent
    a = Agent(name='A', x=0, y=0, agent_id=1, colony_id=1)
    a.hunger = 50.0
    w = _grass_world()
    _food_at(w, 0, 0, 10.0)
    ev = actions.forage(a, w, rng=_FixedRng(13))  # mid band → 2
    assert ev['type'] == 'foraged'
    assert ev['data']['roll'] == 13
    assert ev['data']['amount_taken'] == 2
    assert a.cargo == 2


def test_forage_crit_fail_takes_zero_units():
    # roll=1 must zero out yield even when the tile is full and pouch
    # has room — that's the crit-fail beat in the dice rhythm.
    from app.engine.agent import Agent
    a = Agent(name='A', x=0, y=0, agent_id=1, colony_id=1)
    a.hunger = 50.0
    w = _grass_world()
    tile = _food_at(w, 0, 0, 10.0)
    pre_amount = tile.resource_amount
    ev = actions.forage(a, w, rng=_FixedRng(1))
    assert ev['type'] == 'foraged'
    assert ev['data']['roll'] == 1
    assert ev['data']['amount_taken'] == 0
    assert tile.resource_amount == pre_amount  # tile untouched
    assert a.cargo == 0
    # Hunger still ticks up — eating-on-the-spot doesn't depend on yield.
    assert a.hunger > 50.0


def test_forage_crit_takes_five_when_room_allows():
    from app.engine.agent import Agent
    a = Agent(name='A', x=0, y=0, agent_id=1, colony_id=1)
    a.hunger = 50.0
    w = _grass_world()
    tile = _food_at(w, 0, 0, 10.0)
    ev = actions.forage(a, w, rng=_FixedRng(20))
    assert ev['data']['roll'] == 20
    assert ev['data']['amount_taken'] == 5
    assert a.cargo == 5
    assert tile.resource_amount == 5.0


def test_forage_yield_clamped_by_pouch_room_even_on_crit():
    # Pouch has only 2 slots free → crit (ceiling=5) clamps to 2.
    from app.engine.agent import Agent
    a = Agent(name='A', x=0, y=0, agent_id=1, colony_id=1)
    a.hunger = 50.0
    a.cargo = needs.CARRY_MAX - 2
    w = _grass_world()
    tile = _food_at(w, 0, 0, 10.0)
    ev = actions.forage(a, w, rng=_FixedRng(20))
    assert ev['data']['roll'] == 20
    assert ev['data']['amount_taken'] == 2
    assert a.cargo == needs.CARRY_MAX
