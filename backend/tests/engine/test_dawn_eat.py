from app.engine.agent import Agent
from app.engine.colony import EngineColony
from app.engine.world import World, Tile
from app.engine import actions, config, needs


def _camp_world():
    w = World(5, 5)
    w.tiles = [[Tile(x, y, 'grass') for x in range(5)] for y in range(5)]
    return w


def _colony_at_camp(food_stock=config.INITIAL_FOOD_STOCK):
    return EngineColony(id=1, name='Red', color='#e74c3c',
                        camp_x=1, camp_y=1, food_stock=food_stock)


def test_eat_camp_requires_agent_at_camp():
    w = _camp_world()
    c = _colony_at_camp()
    a = Agent('A', 2, 2, agent_id=1, colony_id=1)
    a.hunger = 50.0
    event = actions.eat_camp(a, c)
    assert event['type'] == 'idled'
    assert c.food_stock == config.INITIAL_FOOD_STOCK
    assert a.hunger == 50.0


def test_eat_camp_requires_sufficient_stock():
    w = _camp_world()
    c = _colony_at_camp(food_stock=config.EAT_COST - 1)
    a = Agent('A', 1, 1, agent_id=1, colony_id=1)
    a.hunger = 50.0
    event = actions.eat_camp(a, c)
    assert event['type'] == 'idled'
    assert a.hunger == 50.0


def test_eat_camp_skipped_when_already_full():
    c = _colony_at_camp()
    a = Agent('A', 1, 1, agent_id=1, colony_id=1)
    a.hunger = needs.NEED_MAX  # already full
    event = actions.eat_camp(a, c)
    assert event['type'] == 'idled'
    assert c.food_stock == config.INITIAL_FOOD_STOCK


def test_eat_camp_cap_fills_hunger_and_debits_stock():
    c = _colony_at_camp()
    a = Agent('A', 1, 1, agent_id=1, colony_id=1)
    a.hunger = 45.0
    event = actions.eat_camp(a, c)
    assert event['type'] == 'ate_from_cache'
    assert event['data']['amount'] == config.EAT_COST
    assert event['data']['colony_id'] == 1
    assert event['data']['hunger_before'] == 45.0
    assert event['data']['hunger_after'] == needs.NEED_MAX
    assert a.hunger == needs.NEED_MAX
    assert c.food_stock == config.INITIAL_FOOD_STOCK - config.EAT_COST
    assert a.ate_this_dawn is True


def test_eat_camp_refuses_second_meal_same_dawn():
    c = _colony_at_camp()
    a = Agent('A', 1, 1, agent_id=1, colony_id=1)
    a.hunger = 45.0
    actions.eat_camp(a, c)  # first meal
    # Fake a further hunger drop; agent is still flagged as ate_this_dawn.
    a.hunger = 50.0
    event = actions.eat_camp(a, c)
    assert event['type'] == 'idled'
    assert c.food_stock == config.INITIAL_FOOD_STOCK - config.EAT_COST   # only one debit


def test_eat_camp_sets_agent_state_eating():
    c = _colony_at_camp()
    a = Agent('A', 1, 1, agent_id=1, colony_id=1)
    a.hunger = 45.0
    actions.eat_camp(a, c)
    assert a.state == actions.STATE_EATING
