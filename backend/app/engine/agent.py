"""Runtime Agent and per-tick driver. Pure Python — no Flask, no DB imports."""
from . import actions, needs


class Agent:
    __slots__ = (
        'id', 'name', 'x', 'y', 'state',
        'hunger', 'energy', 'social', 'health',
        'age', 'alive',
        'colony_id', 'ate_this_dawn',
        'move_cooldown',
        'rogue', 'loner',
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
        # Ticks remaining traversing the current tile. Set by step_toward /
        # explore after a successful step = TERRAIN_MOVE_COST[dest] - 1.
        # While > 0, tick_agent decrements and skips decide_action.
        self.move_cooldown = 0
        # Rogue: social need collapsed to 0 at least once. One-way flag
        # flipped in decay_needs. Rogue agents never seek camp — they
        # wander, forage, and rest wherever they are. No redemption arc.
        self.rogue = False
        # Loner: demo-only promotion flipped at spawn for ~2 agents per
        # sim when population > 4. Scales social decay by
        # LONER_SOCIAL_DECAY_MULT so a visible rogue transition can
        # happen inside a short demo window. All other needs behave
        # normally.
        self.loner = False

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

    rogue = getattr(agent, 'rogue', False)

    if phase == 'night':
        # Non-rogue at camp → full rest. Otherwise rest in the open
        # (worse recovery, but no forced death march back to camp at
        # night when the agent is already tired). Rogue agents ignore
        # camp entirely — home is not theirs anymore.
        if not rogue and colony.is_at_camp(agent.x, agent.y):
            return 'rest'
        return 'rest_outdoors'
    if phase == 'dusk':
        if rogue:
            # Rogue dusk → productive fallthrough (drop into day chain).
            pass
        else:
            return 'step_to_camp'
    if phase == 'dawn':
        if rogue:
            # Rogue dawn → productive fallthrough. No eat_camp (can't
            # access stock), no step_to_camp.
            pass
        else:
            at_camp = colony.is_at_camp(agent.x, agent.y)
            if at_camp:
                if (agent.hunger < needs.NEED_MAX
                        and colony.food_stock >= config.EAT_COST
                        and not agent.ate_this_dawn):
                    return 'eat_camp'
                return 'rest'   # home but ineligible → rest, not a sham step
            return 'step_to_camp'

    # phase == 'day' OR rogue falling through dusk/dawn
    #
    # Social pressure: a non-rogue agent whose social dropped below
    # SOCIAL_LOW interrupts productive work to head home. Only camp
    # refills social (socialise() gates on camp tile), so this is the
    # only behaviour that can prevent social→0→rogue. Rogue agents
    # skip this branch — their social will keep sliding but there's
    # nothing to do about it.
    if not rogue and agent.social < needs.SOCIAL_LOW:
        return 'step_to_camp'

    tile = world.get_tile(agent.x, agent.y)
    if tile.crop_state == 'mature':
        return 'harvest'
    if (tile.crop_state == 'none'
            and tile.resource_amount == 0
            and colony.growing_count < config.MAX_FIELDS_PER_COLONY):
        return 'plant'

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
    if action_name == 'rest_outdoors':
        return actions.rest_outdoors(agent)
    if action_name == 'socialise':
        return actions.socialise(agent, all_agents, colony=colony)
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


def tick_agent(agent, world, all_agents, colonies_by_id=None, *, phase=None, rng):
    """Advance one tick for `agent`.

    `colonies_by_id` is a dict {colony_id: EngineColony}. Indexing by
    agent.colony_id keeps lookup O(1). `phase` comes from cycle.phase_for.

    Legacy callers that pass neither `colonies_by_id` nor `phase` fall back
    to the original pre-cultivation behavior.
    """
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

    # Legacy compat: if either colonies_by_id or phase is None, fall back
    # to the original tick_agent body.
    if colonies_by_id is None or phase is None:
        return _legacy_tick_agent(agent, world, all_agents, rng=rng)

    # New path: phase-aware behavior with colony lookup.
    # Dawn-eat flag is transient: cleared any tick that isn't in the dawn
    # window so next dawn's decide_action sees a fresh eligibility.
    if phase != 'dawn':
        agent.ate_this_dawn = False

    # Hunger decay scales down at night (agents are asleep).
    scale = needs.NIGHT_HUNGER_SCALE if phase == 'night' else 1.0
    needs.decay_needs(agent, hunger_scale=scale)

    if agent.health <= 0:
        events.append(actions.die(agent))
        return events

    # Terrain traversal cost: the agent is mid-crossing. Decay already ran
    # (so sand/stone isn't a free hunger shelter), but the agent can't
    # decide or act this tick. Age still advances — time passes regardless.
    if agent.move_cooldown > 0:
        agent.move_cooldown -= 1
        agent.state = actions.STATE_TRAVERSING
        events.append({
            'type': 'idled',
            'description': f'{agent.name} traversing terrain',
        })
        agent.age += 1
        return events

    # Invariant: when the new path is live, every agent belongs to a colony
    # in the map. A miss means a data-drift bug (stale colony_id, test setup
    # gap). Fail loud — the legacy decide_action fallback would silently
    # bypass phase gates (night→rest, dusk→step_to_camp, dawn→eat_camp).
    colony = colonies_by_id.get(agent.colony_id)
    if colony is None:
        raise KeyError(
            f"Agent {agent.id!r} has colony_id={agent.colony_id!r} "
            f"not in colonies_by_id {list(colonies_by_id)!r}"
        )
    action_name = decide_action(agent, world, colony, phase)
    events.append(execute_action(action_name, agent, world, all_agents, colony, rng=rng))

    agent.age += 1
    return events


def _legacy_tick_agent(agent, world, all_agents, *, rng):
    """Pre-cultivation tick driver. Kept for legacy callers until migration
    to the new phase-aware signature. Identical to the original body before T11."""
    events = []

    needs.decay_needs(agent)

    if agent.health <= 0:
        events.append(actions.die(agent))
        return events

    action_name = decide_action(agent)
    events.append(execute_action(action_name, agent, world, all_agents, rng=rng))

    agent.age += 1
    return events
