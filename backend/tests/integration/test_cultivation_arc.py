from app import db, models
from app.services import simulation_service
from app.engine import config


def test_plant_grow_harvest_lineage(db_session):
    """Force a full plant → grow → harvest arc with one controlled agent.

    Guards:
      * planted event coord matches crop_matured coord
      * harvested event at same coord, crediting the harvesting colony
      * colony.food_stock jumps by HARVEST_YIELD on that harvest
    """
    simulation_service.create_simulation(
        width=20, height=20, seed=1,
        colonies=4, agents_per_colony=3,
    )
    sim = simulation_service.get_current_simulation()
    agent = sim.agents[0]
    colony = sim.colonies[agent.colony_id]

    target = None
    for row in sim.world.tiles:
        for t in row:
            if t.terrain == 'grass' and t.resource_amount == 0 and t.crop_state == 'none':
                target = t
                break
        if target:
            break
    assert target is not None

    agent.x, agent.y = target.x, target.y
    agent.hunger = 80.0
    sim.current_tick = 30  # start of day phase

    events = simulation_service.step_simulation(ticks=1)
    planted = [e for e in events if e['type'] == 'planted']
    assert len(planted) >= 1
    plant_tx = planted[0]['data']['tile_x']
    plant_ty = planted[0]['data']['tile_y']

    matured_event = None
    for _ in range(300):
        agent.x, agent.y = plant_tx, plant_ty
        agent.hunger = 80.0
        agent.social = 80.0
        agent.energy = 80.0
        evs = simulation_service.step_simulation(ticks=1)
        for e in evs:
            if (
                e['type'] == 'crop_matured'
                and e['data']['tile_x'] == plant_tx
                and e['data']['tile_y'] == plant_ty
            ):
                matured_event = e
                break
        if matured_event:
            break
    assert matured_event is not None, 'crop never matured'

    # Harvest loop spans at least one full day-phase after maturity.
    # Mature tick ends inside a day phase; next day phase is 90 ticks later
    # (dusk+night+dawn). 150 iterations guarantees we cross it.
    #
    # Stock delta is captured across the single harvest tick (pre/post the
    # step_simulation call that emits 'harvested'). Harvest runs only in
    # day phase; eat_camp runs only in dawn — so the harvest-tick delta is
    # uncontaminated by eating. A same-tick harvest by another colony
    # member of the same colony could inflate the delta, so we assert
    # >= HARVEST_YIELD rather than equality.
    harvested_event = None
    stock_pre = None
    stock_post = None
    for _ in range(150):
        agent.x, agent.y = plant_tx, plant_ty
        agent.hunger = 80.0
        pre = (
            db.session.query(models.Colony).filter_by(id=colony.id).one().food_stock
        )
        evs = simulation_service.step_simulation(ticks=1)
        for e in evs:
            if e['type'] == 'harvested' and e['data']['tile_x'] == plant_tx:
                harvested_event = e
                stock_pre = pre
                stock_post = (
                    db.session.query(models.Colony)
                    .filter_by(id=colony.id)
                    .one()
                    .food_stock
                )
                break
        if harvested_event:
            break
    assert harvested_event is not None, 'agent never harvested the mature tile'
    assert harvested_event['data']['colony_id'] == colony.id
    assert harvested_event['data']['yield_amount'] == config.HARVEST_YIELD
    assert stock_post - stock_pre >= config.HARVEST_YIELD, (
        f'food_stock delta {stock_post - stock_pre} < HARVEST_YIELD '
        f'{config.HARVEST_YIELD}'
    )
