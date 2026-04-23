"""Runtime Agent and per-tick driver. Pure Python — no Flask, no DB imports."""
from . import actions, config, needs


class Agent:
    __slots__ = (
        'id', 'name', 'x', 'y', 'state',
        'hunger', 'energy', 'social', 'health',
        'age', 'alive',
        'colony_id', 'ate_this_dawn',
        'move_cooldown',
        'rogue', 'loner',
        'cargo',
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
        # Units of food currently in the agent's pouch. 0..CARRY_MAX.
        # Bumped by forage, drained by deposit_cargo at camp. Does NOT
        # feed the agent's own hunger — that's the foraging side-effect
        # that already fills hunger during the gather action.
        self.cargo = 0.0

    def __repr__(self):
        return f"Agent({self.name}@{self.x},{self.y},state={self.state})"


def decide_action(agent, world, colony, phase):
    """Return the name of the action this agent should take this tick.

    Philosophy: agents live in the world, not at camp. The only reasons
    a non-rogue returns home are (a) social need hit SOCIAL_LOW (only
    camp socialise refills it) or (b) a dawn opportunistic eat_camp
    when they happen to already be there. Everything else — foraging,
    harvesting, planting, exploring — happens in the field. Previously
    the dusk/night phases forced a march home where agents sat resting
    for ~60 ticks doing nothing; the demo reads flatter than it should.

    Order of precedence:
      1. Survival (health/hunger/energy crit) — always applies.
      2. Night: rest_outdoors in place (no travel home).
      3. At-camp opportunistic: drop cargo, eat at dawn if hungry.
      4. Social-low (non-rogue) → step_to_camp (the only forced return).
      5. Rogue eat-from-pouch at hunger < MODERATE (they can't eat at camp).
      6. Tile-local productivity (harvest / plant).
      7. Tail: forage → explore.
    """
    # Survival takes precedence over any phase behavior.
    if agent.health < needs.HEALTH_CRITICAL:
        return 'rest' if agent.energy < needs.ENERGY_CRITICAL else 'forage'
    if agent.hunger < needs.HUNGER_CRITICAL:
        return 'forage'
    if agent.energy < needs.ENERGY_CRITICAL:
        return 'rest'

    rogue = getattr(agent, 'rogue', False)
    cargo = getattr(agent, 'cargo', 0.0)
    at_camp = colony.is_at_camp(agent.x, agent.y) if not rogue else False

    # Night: everybody sleeps where they stand. No forced march home.
    # rest_outdoors recovers energy at half-rate, which keeps a natural
    # cost for being caught in the field — but the agent still acts,
    # doesn't trigger the old "traipse home, then rest 60 ticks" loop.
    if phase == 'night':
        return 'rest_outdoors'

    # At-camp opportunistic actions: if the agent happens to already be
    # on their camp tile (typically because social pulled them home),
    # spend the tick usefully before leaving again. Deposit first, eat
    # at dawn if hungry, socialise if social is the reason they came.
    if at_camp:
        if cargo > 0:
            return 'deposit'
        if (phase == 'dawn'
                and agent.hunger < needs.NEED_MAX
                and colony.food_stock >= config.EAT_COST
                and not agent.ate_this_dawn):
            return 'eat_camp'
        if agent.social < needs.SOCIAL_LOW:
            return 'socialise'

    # Social pressure — the only forced return home for a non-rogue.
    # socialise() only refills on the camp tile with a colony-mate, so
    # this branch is what keeps social→0→rogue from being inevitable.
    # Rogue agents skip — their social will keep sliding, nothing to do.
    if not rogue and agent.social < needs.SOCIAL_LOW:
        return 'step_to_camp'

    # Full pouch — non-rogue can't forage any more and should offload.
    # Without this branch a colonist who fills their cargo mid-field just
    # wanders planting/exploring with no way to contribute; their pouch
    # value sits stranded until social or dawn eventually pulls them home.
    # Rogues have no camp so this rule doesn't apply to them — they'll
    # spend cargo via eat_cargo further down the chain.
    if not rogue and cargo >= needs.CARRY_MAX:
        return 'step_to_camp'

    tile = world.get_tile(agent.x, agent.y)
    if tile.crop_state == 'mature':
        return 'harvest'
    if (tile.crop_state == 'none'
            and tile.resource_amount == 0
            and colony.growing_count < config.MAX_FIELDS_PER_COLONY):
        return 'plant'

    # Rogue eat-from-pouch: no camp → cargo is their larder. Trigger at
    # HUNGER_MODERATE so they top up before starvation, and gate on
    # cargo > 0 to avoid firing a sham eat with nothing in the pouch.
    if rogue and cargo > 0 and agent.hunger < needs.HUNGER_MODERATE:
        return 'eat_cargo'

    if agent.hunger < needs.HUNGER_MODERATE:
        return 'forage'
    # No social branch here: at-camp socialise is handled in the at_camp
    # block above, and off-camp social-low already returned
    # 'step_to_camp' earlier. Falling through means social is comfortable
    # (or the agent is rogue, whose social floor is permanent).
    return 'explore'


def execute_action(action_name, agent, world, all_agents, colony, *, rng):
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
    if action_name == 'eat_cargo':
        return actions.eat_cargo(agent)
    if action_name == 'deposit':
        return actions.deposit_cargo(agent, colony)
    if action_name == 'step_to_camp':
        moved = actions.step_toward(agent, colony.camp_x, colony.camp_y, world)
        return {
            'type': 'moved' if moved else 'idled',
            'description': f'{agent.name} headed toward camp',
        }
    return {'type': 'idled', 'description': f'{agent.name} did nothing'}


def tick_agent(agent, world, all_agents, colonies_by_id, *, phase, rng):
    """Advance one tick for `agent`.

    `colonies_by_id` is a dict {colony_id: EngineColony}. Indexing by
    agent.colony_id keeps lookup O(1). `phase` comes from cycle.phase_for.
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

    # Every agent belongs to a colony in the map. A miss means a data-drift
    # bug (stale colony_id, test setup gap). Fail loud at the lookup boundary
    # rather than NPE-ing later in decide_action's at_camp / cargo / plant paths.
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
