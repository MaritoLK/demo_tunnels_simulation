from app.engine import cycle, config, needs


def test_constants_sum_to_day_length():
    assert cycle.TICKS_PER_DAY == cycle.TICKS_PER_PHASE * len(cycle.PHASES)
    assert cycle.TICKS_PER_DAY == 120
    assert cycle.TICKS_PER_PHASE == 30
    assert cycle.PHASES == ('dawn', 'day', 'dusk', 'night')


def test_phase_for_returns_correct_phase_at_boundaries():
    assert cycle.phase_for(0) == 'dawn'
    assert cycle.phase_for(29) == 'dawn'
    assert cycle.phase_for(30) == 'day'
    assert cycle.phase_for(59) == 'day'
    assert cycle.phase_for(60) == 'dusk'
    assert cycle.phase_for(89) == 'dusk'
    assert cycle.phase_for(90) == 'night'
    assert cycle.phase_for(119) == 'night'
    assert cycle.phase_for(120) == 'dawn'   # wraps
    assert cycle.phase_for(240) == 'dawn'


def test_day_for_increments_each_full_cycle():
    assert cycle.day_for(0) == 0
    assert cycle.day_for(119) == 0
    assert cycle.day_for(120) == 1
    assert cycle.day_for(239) == 1
    assert cycle.day_for(240) == 2


def test_config_has_required_balance_constants():
    assert config.HARVEST_YIELD == 9
    assert config.INITIAL_FOOD_STOCK == 18
    assert config.EAT_COST == 6
    assert config.CROP_MATURE_TICKS == 60
    assert config.WILD_RESOURCE_MAX == 5
    assert config.WILD_TILE_DENSITY == 0.15
    assert config.MAX_FIELDS_PER_COLONY == 4
    # Sanity: stock divides evenly by eat cost so "1 day of reliance" is exact
    assert config.INITIAL_FOOD_STOCK % config.EAT_COST == 0


def test_needs_has_night_hunger_scale():
    assert needs.NIGHT_HUNGER_SCALE == 0.5
