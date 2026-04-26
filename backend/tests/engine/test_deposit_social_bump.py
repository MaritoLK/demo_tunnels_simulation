"""Cargo deposit grants a meaningful social bump.

The "I came home with food, the tribe gathers around" event. Combined
with the at-camp passive drip, this is the dominant social refill that
keeps non-loner agents from drifting to rogue over long runs. Rogue
agents are excluded — the flag is a one-way collapse and a deposit
should not reverse it.
"""
from app.engine import actions, needs
from app.engine.agent import Agent
from app.engine.colony import EngineColony


def _colony(camp_x=0, camp_y=0):
    return EngineColony(
        id=1, name='Red', color='#e74c3c',
        camp_x=camp_x, camp_y=camp_y, food_stock=10,
    )


def _camped_agent(cargo=4.0):
    a = Agent('A', 0, 0, agent_id=1, colony_id=1)
    a.cargo = cargo
    a.social = 50.0
    return a


def test_successful_deposit_bumps_social():
    a = _camped_agent()
    pre = a.social
    ev = actions.deposit_cargo(a, _colony())
    assert ev['type'] == 'deposited'
    assert a.social == pre + needs.DEPOSIT_SOCIAL_BUMP


def test_deposit_social_clamps_at_need_max():
    a = _camped_agent()
    a.social = needs.NEED_MAX - 5.0  # less than the bump
    actions.deposit_cargo(a, _colony())
    assert a.social == needs.NEED_MAX


def test_deposit_skips_social_for_rogue_agents():
    a = _camped_agent()
    a.rogue = True
    pre = a.social
    actions.deposit_cargo(a, _colony())
    assert a.social == pre, (
        'rogue is a one-way collapse — depositing should not refill social'
    )


def test_failed_deposit_does_not_bump_social():
    # No cargo → idled → no social bump. Social only fires on the
    # productive path so an off-camp / empty-pouch no-op can't be
    # exploited as a refill.
    a = _camped_agent(cargo=0.0)
    pre = a.social
    ev = actions.deposit_cargo(a, _colony())
    assert ev['type'] == 'idled'
    assert a.social == pre


def test_off_camp_deposit_does_not_bump_social():
    a = _camped_agent()
    a.x, a.y = 5, 5  # off camp
    pre = a.social
    ev = actions.deposit_cargo(a, _colony())
    assert ev['type'] == 'idled'
    assert a.social == pre
