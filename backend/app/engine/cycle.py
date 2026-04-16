"""Day/night cycle math. Pure function of current_tick; no state, no I/O.

TICKS_PER_DAY and TICKS_PER_PHASE are the single source of truth for all
diurnal timing. Keep these invariants:
  - TICKS_PER_DAY == TICKS_PER_PHASE * len(PHASES)
  - PHASES order matches in-world narrative: dawn → day → dusk → night
"""
TICKS_PER_PHASE = 30
PHASES = ('dawn', 'day', 'dusk', 'night')
TICKS_PER_DAY = TICKS_PER_PHASE * len(PHASES)


def phase_for(tick):
    return PHASES[(tick % TICKS_PER_DAY) // TICKS_PER_PHASE]


def day_for(tick):
    return tick // TICKS_PER_DAY
