"""Per-tick passive social refill while standing on the camp tile.

Pre-fix observation (1500-tick diagnostic, 2026-04-26): the socialise
action requires BOTH agents on the camp tile simultaneously, which
almost never aligns. Over a long run every agent eventually drifted
to rogue — including non-loners — because there was no way to
counter the slow steady SOCIAL_DECAY.

Fix: while a non-rogue agent stands on its colony's camp tile, social
refills at PASSIVE_SOCIAL_AT_CAMP_RATE per tick. Tuned at 0.2 — twice
the base SOCIAL_DECAY (0.1) so a non-loner who returns home regularly
holds steady, but loners (4× decay) still drift outward over time so
the rogue mechanic stays meaningful.

Rogue agents skip the refill: rogue is a one-way social-collapse flag,
they're no longer 'in the tribe' and going home doesn't reverse it.
"""
from app.engine import needs
from app.engine.agent import Agent
from app.engine.colony import EngineColony


def _colony(camp_x=5, camp_y=5):
    return EngineColony(
        id=1, name='Red', color='#e74c3c',
        camp_x=camp_x, camp_y=camp_y, food_stock=10,
    )


def _fresh_agent(x, y):
    a = Agent('A', x, y, agent_id=1, colony_id=1)
    a.social = 50.0
    return a


def test_passive_social_refills_on_camp_tile():
    a = _fresh_agent(5, 5)
    pre = a.social
    needs.apply_passive_social(a, _colony(camp_x=5, camp_y=5))
    assert a.social == pre + needs.PASSIVE_SOCIAL_AT_CAMP_RATE


def test_passive_social_does_not_fire_off_camp():
    a = _fresh_agent(8, 8)  # camp at (5,5) — Chebyshev 3, not on camp
    pre = a.social
    needs.apply_passive_social(a, _colony(camp_x=5, camp_y=5))
    assert a.social == pre, (
        f'social bumped off-camp: {pre} → {a.social} (passive should only '
        f'fire on the camp tile itself, not the field area)'
    )


def test_passive_social_skips_rogue_agents():
    a = _fresh_agent(5, 5)
    a.rogue = True
    pre = a.social
    needs.apply_passive_social(a, _colony(camp_x=5, camp_y=5))
    assert a.social == pre, (
        'rogue is a one-way collapse — coming home should not refill social'
    )


def test_passive_social_clamps_at_need_max():
    a = _fresh_agent(5, 5)
    a.social = needs.NEED_MAX - 0.05  # less than the rate
    needs.apply_passive_social(a, _colony(camp_x=5, camp_y=5))
    assert a.social == needs.NEED_MAX, (
        f'social overshot NEED_MAX: {a.social!r}'
    )


def test_passive_social_outpaces_default_decay():
    # The whole point of the constant: net positive while at camp
    # for a non-loner. SOCIAL_DECAY = 0.1 per tick; the at-camp
    # refill must be > that so home time meaningfully refills.
    assert needs.PASSIVE_SOCIAL_AT_CAMP_RATE > needs.SOCIAL_DECAY


def test_round_trip_balance_for_non_loner():
    # Tuning sanity. With a typical 200-tick round trip (1 tick at camp,
    # 199 in field), the combined refill (passive + deposit bump) must
    # at least match the decay so non-loners don't slowly drift to rogue
    # over a long run. Pre-fix the only refill was the rare both-on-camp
    # socialise; non-loners drained to rogue around tick 1000-1500.
    round_trip_ticks = 200
    camp_ticks = 1
    field_ticks = round_trip_ticks - camp_ticks
    field_drain = field_ticks * needs.SOCIAL_DECAY
    refill = (camp_ticks * needs.PASSIVE_SOCIAL_AT_CAMP_RATE
              + needs.DEPOSIT_SOCIAL_BUMP)
    assert refill >= field_drain - 1e-6, (
        f'round-trip net {refill - field_drain} — non-loners would '
        f'still slowly rogue out at this rate'
    )


def test_round_trip_lets_loners_eventually_go_rogue():
    # Loners are the rogue-transition canary. A loner returning home
    # periodically should net negative over a round trip — they decay
    # 4× faster than the refill can keep up with. Pin that the
    # combined refill stays below loner decay so the rogue mechanic
    # remains alive.
    round_trip_ticks = 200
    camp_ticks = 1
    field_ticks = round_trip_ticks - camp_ticks
    loner_decay = needs.SOCIAL_DECAY * needs.LONER_SOCIAL_DECAY_MULT
    field_drain = field_ticks * loner_decay
    refill = (camp_ticks * needs.PASSIVE_SOCIAL_AT_CAMP_RATE
              + needs.DEPOSIT_SOCIAL_BUMP)
    assert refill < field_drain, (
        f'loners would never reach rogue — round trip net = '
        f'{refill - field_drain}'
    )
