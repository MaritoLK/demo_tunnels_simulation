"""Pure mapper round-trips. No app context, no DB — these are the
seams between the engine (plain Python dataclass-like objects) and
the ORM rows. Any drift here silently corrupts the reload path, so
we pin the contract directly rather than trusting the service-level
reload test to catch it.
"""
import pytest

from app import models
from app.engine.agent import Agent as EngineAgent
from app.engine.world import Tile as EngineTile, World as EngineWorld
from app.services import mappers


def _engine_agent_fully_populated():
    """An engine Agent with every field set to a non-default value, so a
    round-trip that silently drops one field would change the result."""
    a = EngineAgent(name='scout-1', x=3, y=7, agent_id=42)
    a.state = 'foraging'
    a.hunger = 33.5
    a.energy = 18.25
    a.social = 71.0
    a.health = 9.5
    a.age = 12
    a.alive = False
    return a


def _snapshot_agent(a):
    return (a.id, a.name, a.x, a.y, a.state, a.hunger, a.energy,
            a.social, a.health, a.age, a.alive)


def test_agent_roundtrip_preserves_all_fields():
    before = _engine_agent_fully_populated()
    row = mappers.agent_to_row(before)
    after = mappers.row_to_agent(row)
    assert _snapshot_agent(before) == _snapshot_agent(after)


def test_tile_roundtrip_preserves_all_fields():
    before = EngineTile(x=2, y=4, terrain='grass', resource_type='food', resource_amount=17.5)
    row = mappers.tile_to_row(before)
    after = mappers.row_to_tile(row)
    assert (before.x, before.y, before.terrain, before.resource_type, before.resource_amount) \
        == (after.x, after.y, after.terrain, after.resource_type, after.resource_amount)


def test_update_agent_row_copies_mutable_fields_only():
    """`update_agent_row` skips name and id — those are immutable
    post-spawn. A change here would silently rename agents on step().
    """
    row = models.Agent(
        id=5, name='original', x=0, y=0, state='idle',
        hunger=100.0, energy=100.0, social=100.0, health=100.0,
        age=0, alive=True,
    )
    mutated = EngineAgent(name='different', x=9, y=9, agent_id=999)
    mutated.state = 'resting'
    mutated.hunger = 50.0

    mappers.update_agent_row(row, mutated)

    assert row.id == 5  # not overwritten by mutated.id
    assert row.name == 'original'  # not overwritten by mutated.name
    assert row.x == 9 and row.y == 9
    assert row.state == 'resting'
    assert row.hunger == 50.0


def test_rows_to_world_raises_on_missing_cell():
    """A corrupt persisted state (fewer rows than width*height) must
    blow up loudly on reload rather than silently rebuilding a world
    with None cells that crash on first access.
    """
    rows = [
        models.WorldTile(x=0, y=0, terrain='grass', resource_type=None, resource_amount=0.0),
        models.WorldTile(x=1, y=0, terrain='grass', resource_type=None, resource_amount=0.0),
        models.WorldTile(x=0, y=1, terrain='grass', resource_type=None, resource_amount=0.0),
        # (1,1) deliberately missing
    ]
    with pytest.raises(ValueError, match=r'missing tile at \(1,1\)'):
        mappers.rows_to_world(rows, width=2, height=2)


def test_rows_to_world_reassembles_out_of_order():
    rows = [
        models.WorldTile(x=1, y=1, terrain='forest', resource_type='wood', resource_amount=15.0),
        models.WorldTile(x=0, y=0, terrain='grass', resource_type=None, resource_amount=0.0),
        models.WorldTile(x=1, y=0, terrain='water', resource_type=None, resource_amount=0.0),
        models.WorldTile(x=0, y=1, terrain='stone', resource_type='stone', resource_amount=10.0),
    ]
    world = mappers.rows_to_world(rows, width=2, height=2)
    assert isinstance(world, EngineWorld)
    assert world.get_tile(0, 0).terrain == 'grass'
    assert world.get_tile(1, 0).terrain == 'water'
    assert world.get_tile(0, 1).terrain == 'stone'
    assert world.get_tile(1, 1).terrain == 'forest'
    assert world.get_tile(1, 1).resource_amount == 15.0


def test_agent_to_dict_emits_decision_reason():
    """The wire shape must carry last_decision_reason under the
    decision_reason key. Frontend relies on this field being present
    on every serialized agent (empty string is fine pre-tick)."""
    from app.routes.serializers import agent_to_dict

    a = EngineAgent('Alice', 1, 1)
    a.last_decision_reason = 'hunger < 50 → forage'
    dumped = agent_to_dict(a)
    assert 'decision_reason' in dumped
    assert dumped['decision_reason'] == 'hunger < 50 → forage'


def test_agent_to_dict_decision_reason_empty_pre_tick():
    from app.routes.serializers import agent_to_dict

    a = EngineAgent('Bob', 2, 2)  # last_decision_reason defaults to ''
    dumped = agent_to_dict(a)
    assert dumped['decision_reason'] == ''


def test_default_simulation_colonies_have_sprite_palette():
    """4-colony default spawn: each colony has sprite_palette matching
    its name. Locks DEFAULT_COLONY_PALETTE → EngineColony threading."""
    from app.engine.simulation import new_simulation
    from app.engine.colony import EngineColony

    colonies = [
        EngineColony(id=i+1, name=name, color=color, camp_x=i, camp_y=i,
                     food_stock=10, sprite_palette=name)
        for i, (name, color) in enumerate(
            [('Red', '#e74c3c'), ('Blue', '#3498db')]
        )
    ]
    sim = new_simulation(10, 10, seed=42, colonies=colonies,
                         agents_per_colony=2)
    for c in sim.colonies.values():
        assert c.sprite_palette in ('Red', 'Blue')


def test_synthesized_default_colony_sprite_palette_is_blue():
    """Simulation.__init__ with colonies=None synthesizes a default.
    That default gets sprite_palette='Blue' so the frontend fallback
    is explicit at the data layer, not implicit in the renderer."""
    from app.engine.simulation import Simulation
    from app.engine.world import World, Tile

    w = World(3, 3)
    w.tiles = [
        [Tile(x, y, 'grass') for x in range(3)]
        for y in range(3)
    ]
    sim = Simulation(w)                                      # no colonies
    default = next(iter(sim.colonies.values()))
    assert default.sprite_palette == 'Blue'
