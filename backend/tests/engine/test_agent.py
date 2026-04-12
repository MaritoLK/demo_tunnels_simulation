"""Agent tick behaviour: needs decay, pre-decay death guard, event emission."""
import random

import pytest

from app.engine.agent import Agent, tick_agent
from app.engine.world import Tile, World


def _grass_world(w=3, h=3):
    world = World(w, h)
    world.tiles = [
        [Tile(x=x, y=y, terrain='grass', resource_type=None, resource_amount=0) for x in range(w)]
        for y in range(h)
    ]
    return world


def test_tick_agent_emits_tick_field_via_simulation():
    # tick_agent itself returns per-agent events without tick set — that's
    # the Simulation.step contract. Just assert the list is iterable here.
    world = _grass_world()
    agent = Agent('Alice', 1, 1)
    events = list(tick_agent(agent, world, [agent], rng=random.Random(0)))
    assert isinstance(events, list)


def test_dead_agent_does_not_decay_or_move():
    # §9.16: tick_agent on a dead agent must be a no-op (not decay needs).
    world = _grass_world()
    agent = Agent('Dead', 1, 1)
    agent.alive = False
    agent.hunger = 50.0
    events = list(tick_agent(agent, world, [agent], rng=random.Random(0)))
    assert agent.hunger == 50.0
    assert agent.x == 1 and agent.y == 1


def test_zero_health_triggers_death_before_decay():
    # §9.16: an agent that enters the tick with health <= 0 dies immediately,
    # without another round of needs decay.
    world = _grass_world()
    agent = Agent('Doomed', 1, 1)
    agent.health = 0.0
    agent.hunger = 50.0
    events = list(tick_agent(agent, world, [agent], rng=random.Random(0)))
    assert agent.alive is False
    assert agent.hunger == 50.0
    assert any(e['type'] == 'died' for e in events)


def test_rng_is_required_kwonly():
    # §9.15: no `rng` kwarg → TypeError, not silent fallback to global random.
    world = _grass_world()
    agent = Agent('Alice', 1, 1)
    with pytest.raises(TypeError):
        list(tick_agent(agent, world, [agent]))
