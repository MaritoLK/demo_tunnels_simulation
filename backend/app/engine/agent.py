"""Runtime Agent and per-tick driver. Pure Python — no Flask, no DB imports."""
from dataclasses import dataclass

from . import actions, config, needs


@dataclass(frozen=True, slots=True)
class Decision:
    """Result of a decision tick. `action` is the action-name the engine
    picked; `reason` is a short human-readable explanation of which
    branch of the priority ladder fired. Both come from one ladder walk
    inside decide_action — never two ladder walks (i.e. don't grow a
    parallel reason_for() function; see CLAUDE.md §Design principles)."""
    action: str
    reason: str


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


def decide_action(agent, world, colony, phase) -> Decision:
    """Return the Decision (action-name + reason) for this agent this tick.

    Priority ladder (first match wins):
      1. Survival (health / hunger / energy crits).
      2. Night → rest_outdoors in place.
      3. At-camp opportunistic (deposit / eat / socialise).
      4. Social-low off-camp → step_to_camp.
      5. Cargo-full off-camp → step_to_camp.
      6. Tile-local (harvest / plant).
      7. Rogue eat-from-pouch.
      8. Tail (forage / explore).

    Design notes — why this shape:
      * Agents live in the world, not at camp. The only forced returns
        home are social pressure (only at-camp socialise refills it) and
        a full cargo (so colonists eventually deposit instead of stranding
        their pouch in the field).
      * Night is rest-in-place, not march-home — the prior dusk/night
        forced-march loop ate ~60 ticks of demo time on idle pawns.
      * Rogue agents skip the camp branches entirely; their social need
        floor is permanent so step-to-camp would be busywork.

    Every branch returns one Decision literal so action + reason cannot
    drift. See CLAUDE.md §Design principles and the spec's
    §Single-source-of-truth section for the full reason-string table.
    """
    hc = int(needs.HEALTH_CRITICAL)
    ec = int(needs.ENERGY_CRITICAL)
    hu_c = int(needs.HUNGER_CRITICAL)
    hu_m = int(needs.HUNGER_MODERATE)
    sl = int(needs.SOCIAL_LOW)

    # 1. Survival
    if agent.health < needs.HEALTH_CRITICAL:
        if agent.energy < needs.ENERGY_CRITICAL:
            return Decision('rest', f'health < {hc}, energy < {ec} → rest')
        return Decision('forage', f'health < {hc} → forage to recover')
    if agent.hunger < needs.HUNGER_CRITICAL:
        return Decision('forage', f'hunger < {hu_c} → forage now')
    if agent.energy < needs.ENERGY_CRITICAL:
        return Decision('rest', f'energy < {ec} → rest')

    at_camp = colony.is_at_camp(agent.x, agent.y) if not agent.rogue else False

    # 2. Night
    if phase == 'night':
        return Decision('rest_outdoors', 'night phase → rest in place')

    # 3. At-camp opportunistic
    if at_camp:
        if agent.cargo > 0:
            return Decision('deposit', f'at camp, cargo {agent.cargo:.1f} → deposit')
        if (phase == 'dawn'
                and agent.hunger < needs.NEED_MAX
                and colony.food_stock >= config.EAT_COST
                and not agent.ate_this_dawn):
            return Decision('eat_camp', 'dawn at camp → eat stock')
        if agent.social < needs.SOCIAL_LOW:
            return Decision('socialise', f'at camp, social < {sl} → socialise')

    # 4. Social-low off-camp
    if not agent.rogue and agent.social < needs.SOCIAL_LOW:
        return Decision('step_to_camp', f'social < {sl} → head to camp')

    # 5. Cargo-full off-camp
    if not agent.rogue and agent.cargo >= needs.CARRY_MAX:
        return Decision('step_to_camp', 'cargo full → head to camp')

    # 6. Tile-local
    tile = world.get_tile(agent.x, agent.y)
    if tile.crop_state == 'mature':
        return Decision('harvest', 'mature crop → harvest')
    if (tile.crop_state == 'none'
            and tile.resource_amount == 0
            and colony.growing_count < config.MAX_FIELDS_PER_COLONY):
        return Decision('plant', 'empty tile → plant')

    # 7. Rogue eat-from-pouch
    if agent.rogue and agent.cargo > 0 and agent.hunger < needs.HUNGER_MODERATE:
        return Decision('eat_cargo', f'rogue, hunger < {hu_m} → eat from pouch')

    # 8. Tail
    if agent.hunger < needs.HUNGER_MODERATE:
        return Decision('forage', f'hunger < {hu_m} → forage')
    return Decision('explore', 'all needs ok → explore')


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
    decision = decide_action(agent, world, colony, phase)
    events.append(execute_action(decision.action, agent, world, all_agents, colony, rng=rng))

    agent.age += 1
    return events
