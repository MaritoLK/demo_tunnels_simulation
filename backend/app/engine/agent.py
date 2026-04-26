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
        'cargo_food', 'cargo_wood', 'cargo_stone',
        'last_decision_reason',
        'food_memory',
        'tiles_walked',
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
        # Per-resource pouches. Combined weight (food*1 + wood*2 +
        # stone*3) is capped at CARRY_MAX via needs.cargo_weight. Each
        # resource has its own gather action (forage / gather_wood /
        # gather_stone) and the camp deposit drains all three at once.
        # Wood/stone don't feed the agent's hunger — only forage does
        # the gather-time hunger restore — so eat_cargo pulls only
        # from cargo_food.
        self.cargo_food = 0.0
        self.cargo_wood = 0.0
        self.cargo_stone = 0.0
        # Populated per tick by tick_agent after decide_action. Empty string
        # before the first tick so serializer + UI can treat absence as
        # "no decision yet" without special-casing None.
        self.last_decision_reason = ''
        # Recent productive forage tiles (most-recent-last). When the
        # agent falls into the explore branch, it wanders toward the
        # nearest remembered tile rather than picking a random
        # neighbor — turns "all needs ok → drift" into "all needs ok
        # → patrol the colony's known caches." Capped to FOOD_MEMORY_MAX
        # so a long run doesn't grow the slot unbounded; in-memory only
        # for now (re-fills naturally on the next successful forage).
        self.food_memory = []
        # Lifetime tile-step counter. Incremented in tick_agent each
        # time a decision actually moved the agent. Drives the walk-
        # skill tier that scales fog reveal radius (1 → 2 → 3) — a
        # veteran scout uncovers a wider area than a freshly-spawned
        # one. Persisted on the row so reloads keep the tier intact.
        self.tiles_walked = 0

    def __repr__(self):
        return f"Agent({self.name}@{self.x},{self.y},state={self.state})"


def decide_action(agent, world, colony, phase) -> Decision:
    """Return the Decision (action-name + reason) for this agent this tick.

    Priority ladder (first match wins):
      1. Survival (health / hunger / energy crits).
      2. Night → rest_outdoors in place.
      3. At-camp opportunistic (deposit / eat / upgrade / socialise).
      4. Social-low off-camp → step_to_camp.
      5. Cargo-full off-camp → step_to_camp.
      6. Harvest own tile.
      6b. Step toward known mature crop.
      7. Opportunistic forage (food adjacent + pouch room).
      7b. Own-tile wood / stone gather.
      8. Plant own tile.
      9. Rogue eat-from-pouch.
     10. Tail (forage / explore).

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
        # Pouch food first: an agent with food on hand should never
        # starve to death holding food. The 1700-tick diagnostic on
        # 2026-04-26 caught 17 deaths where agents with full pouches
        # exhausted local food and died during the BFS-then-explore
        # fallback. Survival ranks above resource conservation.
        if agent.cargo_food > 0:
            return Decision('eat_cargo', f'health < {hc} → eat from pouch')
        return Decision('forage', f'health < {hc} → forage to recover')
    if agent.hunger < needs.HUNGER_CRITICAL:
        if agent.cargo_food > 0:
            return Decision('eat_cargo', f'hunger < {hu_c} → eat from pouch')
        return Decision('forage', f'hunger < {hu_c} → forage now')
    if agent.energy < needs.ENERGY_CRITICAL:
        return Decision('rest', f'energy < {ec} → rest')

    at_camp = colony.is_at_camp(agent.x, agent.y) if not agent.rogue else False

    # 2. Night
    if phase == 'night':
        return Decision('rest_outdoors', 'night phase → rest in place')

    # 3. At-camp opportunistic
    if at_camp:
        if needs.cargo_weight(agent) > 0:
            return Decision(
                'deposit',
                f'at camp, cargo weight {needs.cargo_weight(agent):.1f} → deposit',
            )
        if (phase == 'dawn'
                and agent.hunger < needs.NEED_MAX
                and colony.food_stock >= config.tier_benefit(colony, 'eat_cost')
                and not agent.ate_this_dawn):
            return Decision('eat_camp', 'dawn at camp → eat stock')
        # Camp tier upgrade — agent at home with the colony having
        # banked enough wood + stone to reach the next tier. Sits
        # before socialise so an idle 'visiting' agent prefers
        # productive infrastructure work over chatting.
        if actions.can_upgrade(colony):
            return Decision(
                'upgrade_camp',
                f'at camp, can afford tier {colony.tier + 1} → upgrade',
            )
        if agent.social < needs.SOCIAL_LOW:
            return Decision('socialise', f'at camp, social < {sl} → socialise')

    # 4. Social-low off-camp
    if not agent.rogue and agent.social < needs.SOCIAL_LOW:
        return Decision('step_to_camp', f'social < {sl} → head to camp')

    # 5. Cargo-full off-camp
    cap = needs.carry_max_for(colony)
    if not agent.rogue and needs.cargo_weight(agent) >= cap:
        return Decision('step_to_camp', 'cargo full → head to camp')

    # 6. Tile-local: harvest first (mature crops outrank wild food —
    # higher yield, locks in a colony investment).
    tile = world.get_tile(agent.x, agent.y)
    if tile.crop_state == 'mature':
        return Decision('harvest', 'mature crop → harvest')

    # 6b. Walk toward a known mature crop. Without this rung crops
    # planted under PLANT_RADIUS_FROM_CAMP cluster in a small patch
    # that agents on forage / explore routes rarely cross — the
    # integration arc test went 0/4 colonies harvesting until this
    # was added. Sits below cargo-full (don't ditch a full pouch
    # to chase a crop) and above opportunistic forage (mature crop
    # outranks wild food on yield + colony investment).
    if actions.has_reachable_mature_crop(agent, world):
        return Decision('step_to_harvest', 'mature crop reachable → walk over')

    # 7. Opportunistic forage: food in reach + pouch room → grab it on
    # sight, even when hunger is fine. Food generation is sparse (the
    # demo halved spawn rate to make caches feel valuable); walking
    # past a wild-food tile because the agent isn't hungry leaves
    # precious supply for the world to clean up while the colony
    # starves later. Sits ABOVE plant so we never sacrifice immediate
    # food for a multi-tick crop investment, and ABOVE the rogue
    # eat-from-pouch / tail rungs so it overrides "all needs ok →
    # explore".
    weight = needs.cargo_weight(agent)
    if weight + needs.FOOD_WEIGHT <= cap and actions.adjacent_food_tile(agent, world) is not None:
        return Decision('forage', 'food in reach → forage on sight')

    # 7b. Own-tile wood / stone gather. Triggers when the agent
    # happens to be standing on a forest or stone tile during their
    # explore route. Pouch must have room for at least one unit of
    # the resource — wood costs 2 weight, stone 3, so a near-full
    # food pouch can be too heavy to carry even one log. Outranks
    # plant — wood/stone is an immediate gain, plant is a multi-tick
    # investment.
    if (tile.resource_type == 'wood' and tile.resource_amount > 0
            and weight + needs.WOOD_WEIGHT <= cap):
        return Decision('gather_wood', 'wood underfoot → gather')
    if (tile.resource_type == 'stone' and tile.resource_amount > 0
            and weight + needs.STONE_WEIGHT <= cap):
        return Decision('gather_stone', 'stone underfoot → gather')

    # 8. Plant: empty tile + free field slot + within camp's field radius
    # → start a crop. The full gate lives in actions.is_plantable so the
    # ladder check and the plant action's re-check share one source of
    # truth (CLAUDE.md design principle).
    if actions.is_plantable(tile, colony):
        return Decision('plant', 'empty tile near camp → plant')

    # 9. Rogue eat-from-pouch
    if agent.rogue and agent.cargo_food > 0 and agent.hunger < needs.HUNGER_MODERATE:
        return Decision('eat_cargo', f'rogue, hunger < {hu_m} → eat from pouch')

    # 10. Tail
    if agent.hunger < needs.HUNGER_MODERATE:
        return Decision('forage', f'hunger < {hu_m} → forage')
    return Decision('explore', 'all needs ok → explore')


def execute_action(action_name, agent, world, all_agents, colony, *, rng):
    # Default state for the tick is IDLE. Each action overrides on a
    # productive success — rest sets RESTING, forage sets FORAGING, etc.
    # Keeping the reset here (rather than scattering `agent.state =
    # STATE_IDLE` across every action's honest-action guard) makes
    # the contract one-line obvious: "if the action did real work it
    # writes its own state, otherwise the visual reads idle". Pre-fix
    # the rendered visual lagged the truth — `rest()` returning idled
    # on full energy left state='resting', and `step_to_camp` never
    # wrote state at all, so a 💤 glyph followed the agent home.
    agent.state = actions.STATE_IDLE
    if action_name == 'forage':
        return actions.forage(agent, world, rng=rng, colony=colony)
    if action_name == 'rest':
        return actions.rest(agent, colony)
    if action_name == 'rest_outdoors':
        return actions.rest_outdoors(agent)
    if action_name == 'socialise':
        return actions.socialise(agent, all_agents, colony=colony)
    if action_name == 'explore':
        return actions.explore(agent, world, colony, rng=rng)
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
    if action_name == 'gather_wood':
        return actions.gather_wood(agent, world, colony)
    if action_name == 'gather_stone':
        return actions.gather_stone(agent, world, colony)
    if action_name == 'upgrade_camp':
        return actions.upgrade_camp(agent, colony)
    if action_name == 'step_to_camp':
        moved = actions.step_toward(agent, colony.camp_x, colony.camp_y, world, colony)
        if moved:
            # Mid-trek visual: agent is moving with purpose. Renderer
            # maps STATE_EXPLORING to a green '?' glyph — close enough
            # to "going somewhere" without inventing a dedicated state.
            agent.state = actions.STATE_EXPLORING
        return {
            'type': 'moved' if moved else 'idled',
            'description': f'{agent.name} headed toward camp',
        }
    if action_name == 'step_to_harvest':
        return actions.step_toward_mature_crop(agent, world, colony)
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
        events.append(actions.die(agent, cause='starvation'))
        return events

    # Age-out: agents past MAX_AGE_TICKS die a natural death. Checked
    # before need decay so the cause is unambiguous — an agent who
    # ages out the same tick they would have starved gets a clean
    # 'old age' event instead of fighting starvation for the credit.
    if agent.age >= config.MAX_AGE_TICKS:
        events.append(actions.die(agent, cause='old age'))
        return events

    # Dawn-eat flag is transient: cleared any tick that isn't in the dawn
    # window so next dawn's decide_action sees a fresh eligibility.
    if phase != 'dawn':
        agent.ate_this_dawn = False

    # Hunger decay scales down at night (agents are asleep).
    scale = needs.NIGHT_HUNGER_SCALE if phase == 'night' else 1.0
    needs.decay_needs(agent, hunger_scale=scale)

    # At-camp passive social refill — runs every tick, not gated by
    # decide_action. Without this the socialise action almost never
    # fires (both-on-camp coincidence) and every agent eventually
    # drifts to rogue. Looking up colony here once so both passive
    # social AND the later decide_action share the same reference.
    colony = colonies_by_id.get(agent.colony_id)
    if colony is None:
        raise KeyError(
            f"Agent {agent.id!r} has colony_id={agent.colony_id!r} "
            f"not in colonies_by_id {list(colonies_by_id)!r}"
        )
    needs.apply_passive_social(agent, colony)

    if agent.health <= 0:
        events.append(actions.die(agent, cause='starvation'))
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

    # `colony` was already resolved (and validated) above, before the
    # passive-social step. Reused here so the lookup is only paid once
    # per tick and the same reference flows into decide_action.
    decision = decide_action(agent, world, colony, phase)
    agent.last_decision_reason = decision.reason
    pre_x, pre_y = agent.x, agent.y
    events.append(execute_action(decision.action, agent, world, all_agents, colony, rng=rng))
    # Walk-skill counter + per-step energy cost: both gated on a real
    # position change so a cooldown-locked tick doesn't get billed.
    # Pre-fix energy was effectively decorative — constant decay alone
    # never threatened to drain the meter. The per-step cost makes
    # active agents feel the work.
    if (agent.x, agent.y) != (pre_x, pre_y):
        agent.tiles_walked += 1
        agent.energy = max(0.0, agent.energy - needs.ENERGY_PER_STEP)

    agent.age += 1
    return events
