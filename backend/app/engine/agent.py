"""Runtime Agent and per-tick driver. Pure Python — no Flask, no DB imports."""
from . import actions, needs


class Agent:
    __slots__ = (
        'id', 'name', 'x', 'y', 'state',
        'hunger', 'energy', 'social', 'health',
        'age', 'alive',
        'colony_id', 'ate_this_dawn',
    )

    def __init__(self, name, x, y, agent_id=None, colony_id=None):
        self.id = agent_id
        self.name = name
        self.x = x
        self.y = y
        self.state = actions.STATE_IDLE
        self.hunger = needs.NEED_MAX
        self.energy = needs.NEED_MAX
        self.social = needs.NEED_MAX
        self.health = needs.NEED_MAX
        self.age = 0
        self.alive = True
        self.colony_id = colony_id
        # Transient: set True when agent emits ate_from_cache in dawn phase;
        # cleared by tick_agent when phase != 'dawn'. Keeps one-meal-per-day
        # enforced without persisting a per-agent counter.
        self.ate_this_dawn = False

    def __repr__(self):
        return f"Agent({self.name}@{self.x},{self.y},state={self.state})"


def decide_action(agent, world=None, colony=None, phase=None):
    """Return the name of the action this agent should take this tick.

    Order of precedence:
      1. Survival (health/hunger/energy crit) — always applies.
      2. Phase gating:
         - dawn: eat at camp if possible, else walk there
         - dusk: walk to camp
         - night: rest (engine-wide; hunger decay halved in tick_agent)
         - day: extended productive chain (harvest > plant > ...)
      3. Existing tail (hunger_mod forage → social → explore).

    Legacy single-arg callers (pre-cultivation sims, audit scripts) hit
    the `colony is None` path and get the classic chain. This preserves
    backwards compat while T11/T12 finish wiring phase + colony through.
    """
    from . import config

    if colony is None:
        return _legacy_decide_action(agent)
    if world is None:
        # Defensive guard: new path requires world. Fall back to legacy
        # chain rather than NPE-ing on world.get_tile in the 'day' branch.
        return _legacy_decide_action(agent)

    # Survival takes precedence over any phase behavior.
    if agent.health < needs.HEALTH_CRITICAL:
        return 'rest' if agent.energy < needs.ENERGY_CRITICAL else 'forage'
    if agent.hunger < needs.HUNGER_CRITICAL:
        return 'forage'
    if agent.energy < needs.ENERGY_CRITICAL:
        return 'rest'

    if phase == 'night':
        return 'rest'
    if phase == 'dusk':
        return 'step_to_camp'
    if phase == 'dawn':
        at_camp = colony.is_at_camp(agent.x, agent.y)
        if at_camp:
            if (agent.hunger < needs.NEED_MAX
                    and colony.food_stock >= config.EAT_COST
                    and not agent.ate_this_dawn):
                return 'eat_camp'
            return 'rest'   # home but ineligible → rest, not a sham step
        return 'step_to_camp'

    # phase == 'day' — productive branches
    tile = world.get_tile(agent.x, agent.y)
    if tile.crop_state == 'mature':
        return 'harvest'
    if (tile.crop_state == 'none'
            and tile.resource_amount == 0
            and colony.growing_count < config.MAX_FIELDS_PER_COLONY):
        return 'plant'

    # Existing hunger/social/explore fallthrough
    if agent.hunger < needs.HUNGER_MODERATE:
        return 'forage'
    if agent.social < needs.SOCIAL_LOW:
        return 'socialise'
    return 'explore'


def _legacy_decide_action(agent):
    """Pre-cultivation decision chain. Kept for legacy one-arg callers
    (test_agent.py suite, audit/*.py scripts) until they migrate to the
    new signature. Identical to the original body before T10."""
    if agent.health < needs.HEALTH_CRITICAL:
        return 'rest' if agent.energy < needs.ENERGY_CRITICAL else 'forage'
    if agent.hunger < needs.HUNGER_CRITICAL:
        return 'forage'
    if agent.energy < needs.ENERGY_CRITICAL:
        return 'rest'
    if agent.hunger < needs.HUNGER_MODERATE:
        return 'forage'
    if agent.social < needs.SOCIAL_LOW:
        return 'socialise'
    return 'explore'


def execute_action(action_name, agent, world, all_agents, colony=None, *, rng):
    if action_name == 'forage':
        return actions.forage(agent, world, rng=rng)
    if action_name == 'rest':
        return actions.rest(agent)
    if action_name == 'socialise':
        return actions.socialise(agent, all_agents)
    if action_name == 'explore':
        return actions.explore(agent, world, rng=rng)
    if action_name == 'plant':
        return actions.plant(agent, world, colony)
    if action_name == 'harvest':
        return actions.harvest(agent, world, colony)
    if action_name == 'eat_camp':
        return actions.eat_camp(agent, colony)
    if action_name == 'step_to_camp':
        moved = actions.step_toward(agent, colony.camp_x, colony.camp_y, world)
        return {
            'type': 'moved' if moved else 'idled',
            'description': f'{agent.name} headed toward camp',
        }
    return {'type': 'idled', 'description': f'{agent.name} did nothing'}


def tick_agent(agent, world, all_agents, *, rng):
    if not agent.alive:
        return []

    events = []

    # Pre-decay death check: an agent that entered the tick already at
    # zero health is semantically a corpse. Don't decay its needs first —
    # die immediately. The post-decay check below still catches the
    # common case where starvation drives health across the threshold
    # *this tick*.
    if agent.health <= 0:
        events.append(actions.die(agent))
        return events

    needs.decay_needs(agent)

    if agent.health <= 0:
        events.append(actions.die(agent))
        return events

    action_name = decide_action(agent)
    events.append(execute_action(action_name, agent, world, all_agents, rng=rng))

    agent.age += 1
    return events
