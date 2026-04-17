"""Loner flag: 2 agents per sim (when total > 4) socially decay faster.

Why: demo windows are short — SOCIAL_DECAY = 0.1/tick takes 1000 ticks
to reach 0, so the rogue pathway rarely fires inside a 5-minute session.
Promoting two randomly-chosen agents to 'loner' gives them a higher
per-tick social decay (LONER_SOCIAL_DECAY_MULT), so at least some agents
visibly trend toward rogue during the demo without touching the rest
of the colony's baseline behaviour.

Chosen at spawn, deterministically via sim.rng_spawn.
"""
import pytest

from app.engine import needs
from app.engine.agent import Agent
from app.engine.colony import EngineColony
from app.engine.simulation import new_simulation


def _colony(cid, name, cx, cy):
    return EngineColony(id=cid, name=name, color='#000',
                        camp_x=cx, camp_y=cy, food_stock=20)


def test_agent_starts_non_loner():
    a = Agent('A', 0, 0, agent_id=1, colony_id=1)
    assert a.loner is False


def test_decay_needs_standard_social_rate_for_non_loner():
    a = Agent('A', 0, 0, agent_id=1, colony_id=1)
    a.social = 50.0
    needs.decay_needs(a)
    assert 50.0 - a.social == pytest.approx(needs.SOCIAL_DECAY)


def test_decay_needs_scales_social_decay_for_loner():
    a = Agent('A', 0, 0, agent_id=1, colony_id=1)
    a.loner = True
    a.social = 50.0
    needs.decay_needs(a)
    drop = 50.0 - a.social
    assert drop == pytest.approx(needs.SOCIAL_DECAY * needs.LONER_SOCIAL_DECAY_MULT)


def test_loner_flag_does_not_affect_hunger_or_energy():
    a = Agent('A', 0, 0, agent_id=1, colony_id=1)
    a.loner = True
    a.hunger = a.energy = 80.0
    needs.decay_needs(a)
    assert 80.0 - a.hunger == pytest.approx(needs.HUNGER_DECAY)
    assert 80.0 - a.energy == pytest.approx(needs.ENERGY_DECAY)


def test_small_sim_under_four_agents_picks_zero_loners():
    """<=4 agents: no loner promotion. Keeps small test sims and
    legacy single-colony setups untouched."""
    colonies = [_colony(1, 'R', 0, 0)]
    sim = new_simulation(10, 10, seed=123, colonies=colonies, agents_per_colony=4)
    assert len(sim.agents) == 4
    assert sum(1 for a in sim.agents if a.loner) == 0


def test_sim_over_four_agents_picks_exactly_two_loners():
    colonies = [_colony(1, 'R', 0, 0), _colony(2, 'B', 9, 9)]
    sim = new_simulation(10, 10, seed=7, colonies=colonies, agents_per_colony=3)
    assert len(sim.agents) == 6
    assert sum(1 for a in sim.agents if a.loner) == 2


def test_loner_selection_is_deterministic_with_seed():
    colonies = [_colony(1, 'R', 0, 0), _colony(2, 'B', 9, 9)]
    sim_a = new_simulation(10, 10, seed=42, colonies=colonies, agents_per_colony=3)
    sim_b = new_simulation(10, 10, seed=42, colonies=colonies, agents_per_colony=3)
    loners_a = [a.name for a in sim_a.agents if a.loner]
    loners_b = [a.name for a in sim_b.agents if a.loner]
    assert loners_a == loners_b
