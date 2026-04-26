"""Agents actively path to mature crops instead of waiting to randomly
walk over one.

Pre-fix observation (CI 2026-04-26): with PLANT_RADIUS_FROM_CAMP
clustering crops in a tight area near each camp, the integration arc
test went from 'multi-colony harvests reliably' to '0 harvests in
300 ticks'. Agents kept planting + maturing but never stepped onto
the mature tiles to harvest them, because their forage / explore
routes don't pass through the camp's plot area.

Fix: a new 'step_to_harvest' decision rung between the own-tile
harvest gate and opportunistic forage. When a mature crop is
reachable within PATH_SEARCH_HORIZON, the agent BFS-routes one step
toward it. The own-tile harvest then fires next tick when they
arrive. Cleanly mirrors the BFS-toward-food behaviour in forage.
"""
import random

from app.engine import actions
from app.engine.agent import Agent, decide_action, execute_action
from app.engine.colony import EngineColony
from app.engine.world import Tile, World


def _grass(width=20, height=20):
    w = World(width, height)
    w.tiles = [
        [Tile(x, y, 'grass') for x in range(width)]
        for y in range(height)
    ]
    return w


def _colony():
    return EngineColony(
        id=1, name='Red', color='#e74c3c',
        camp_x=3, camp_y=3, food_stock=10,
    )


def _agent(x, y):
    a = Agent('A', x, y, agent_id=1, colony_id=1)
    a.hunger = 80.0
    a.energy = 80.0
    a.social = 80.0
    a.health = 100.0
    return a


def test_decide_action_picks_step_to_harvest_when_mature_crop_reachable():
    a = _agent(10, 10)
    w = _grass()
    # Mature crop near camp, within walkable path of the agent.
    crop = w.get_tile(5, 5)
    crop.crop_state = 'mature'
    crop.crop_colony_id = 1
    decision = decide_action(a, w, _colony(), 'day')
    assert decision.action == 'step_to_harvest', (
        f'expected step_to_harvest, got {decision.action!r} ({decision.reason!r})'
    )


def test_step_to_harvest_walks_one_tile_toward_crop():
    a = _agent(10, 10)
    w = _grass()
    crop = w.get_tile(5, 5)
    crop.crop_state = 'mature'
    pre = (a.x, a.y)
    ev = execute_action('step_to_harvest', a, w, [a], _colony(), rng=random.Random(0))
    assert ev['type'] == 'moved'
    # Manhattan distance to crop must have shrunk by exactly 1.
    pre_dist = abs(pre[0] - 5) + abs(pre[1] - 5)
    post_dist = abs(a.x - 5) + abs(a.y - 5)
    assert post_dist == pre_dist - 1, (
        f'expected one-tile progress toward crop: '
        f'pre={pre} ({pre_dist}), post=({a.x},{a.y}) ({post_dist})'
    )


def test_arrival_on_mature_tile_picks_harvest():
    # Agent right next to crop. Step lands on the mature tile.
    # Next decision should be 'harvest', not 'step_to_harvest'.
    a = _agent(5, 6)
    w = _grass()
    w.get_tile(5, 5).crop_state = 'mature'
    w.get_tile(5, 5).crop_colony_id = 1
    decision = decide_action(a, w, _colony(), 'day')
    assert decision.action == 'step_to_harvest'
    # Move there.
    a.y = 5
    decision_after = decide_action(a, w, _colony(), 'day')
    assert decision_after.action == 'harvest'


def test_no_step_to_harvest_when_no_mature_crops_anywhere():
    a = _agent(10, 10)
    w = _grass()  # no crops at all
    decision = decide_action(a, w, _colony(), 'day')
    # Falls through past harvest / step_to_harvest / opportunistic
    # forage / plant. With agent far from camp (Chebyshev 7 from
    # (3,3) — beyond PLANT_RADIUS_FROM_CAMP=4), plant is gated. So
    # the tail explore branch fires.
    assert decision.action != 'step_to_harvest'


def test_step_to_harvest_idles_if_crop_unreachable_mid_tick():
    # Edge case: crop becomes unreachable between decide_action and
    # the action call. The action must idle gracefully rather than
    # NPE on a None step.
    a = _agent(10, 10)
    w = _grass()
    # No mature crops at all: the action's own BFS finds nothing.
    ev = execute_action('step_to_harvest', a, w, [a], _colony(), rng=random.Random(0))
    assert ev['type'] == 'idled'


def test_cargo_full_does_not_pick_step_to_harvest():
    # Cargo-full is rung 5. It must outrank step_to_harvest (which
    # sits at rung 6b). Agent must head to camp first to deposit,
    # otherwise they'd dance between mature crops without ever
    # bringing pouch home.
    from app.engine import needs
    a = _agent(10, 10)
    a.cargo = needs.CARRY_MAX
    w = _grass()
    w.get_tile(5, 5).crop_state = 'mature'
    decision = decide_action(a, w, _colony(), 'day')
    assert decision.action == 'step_to_camp'
