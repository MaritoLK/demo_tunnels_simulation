from app.engine import cycle


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
