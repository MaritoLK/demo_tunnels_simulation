"""Need-tuning constants and the per-tick decay function. Pure Python."""
from . import config
HUNGER_DECAY = 0.5
ENERGY_DECAY = 0.3
# Lowered from 0.1 → 0.02 so non-loners stay stable across a long demo
# even when round trips between deposits run 500+ ticks. Combined with
# DEPOSIT_SOCIAL_BUMP (event-driven refill) the meter holds up; without
# the lower base every agent eventually drained to rogue regardless of
# refill events. Loners still reach rogue via LONER_SOCIAL_DECAY_MULT.
SOCIAL_DECAY = 0.02

# Night-phase hunger scaling: agents decay slower while sleeping. Applied
# in tick_agent via cycle.phase_for; keeps the constant here so needs.py
# remains the single home for all decay-related tuning.
NIGHT_HUNGER_SCALE = 0.5

# Loner: promoted at spawn (see simulation.new_simulation). Their social
# need decays at this multiple of SOCIAL_DECAY, so rogue transitions
# happen inside a short demo window. Bumped from 4.0 → 10.0 alongside
# the SOCIAL_DECAY drop — keeps loners reaching rogue inside ~600 ticks
# (5 min at default speed with night auto-speedup) while non-loners
# hold steady forever.
LONER_SOCIAL_DECAY_MULT = 10.0

STARVATION_HEALTH_DAMAGE = 2.0

# Passive health regen: a well-fed agent slowly recovers. Without this,
# any agent that ever starves stays damaged forever — the "zombie" state
# where health is below max but never moves. Symmetric with the starvation
# damage branch: decay_needs is the one place health changes each tick.
PASSIVE_HEAL_RATE = 0.3

FORAGE_HUNGER_RESTORE = 20.0
REST_ENERGY_RESTORE = 5.0
# Energy debited on every successful position change, on top of the
# constant per-tick ENERGY_DECAY. Pre-fix the constant decay alone
# (-0.3/tick = -36 over a 120-tick day) was easily covered by night
# rest_outdoors (+75 over a 30-tick night) — energy never gated a
# decision, the meter was decoration. With ENERGY_PER_STEP=1.0 a busy
# foraging day burns ~85, more than night recovery, so agents need
# the occasional day rest. Idle / cooldown ticks pay only the constant
# decay so an agent stuck mid-traversal doesn't get double-billed.
ENERGY_PER_STEP = 1.0
# Per-tick social refill while a non-rogue agent stands on the colony's
# camp tile. Mild constant drip — the dominant social-refill mechanism
# is DEPOSIT_SOCIAL_BUMP, fired once per cargo deposit. Passive is the
# safety net for agents who linger at camp without depositing.
PASSIVE_SOCIAL_AT_CAMP_RATE = 1.0

# Social bump on a successful deposit_cargo. The natural "I came home
# with food, the tribe gathers around" moment. Sized so a typical
# 200-tick round trip nets a small surplus for non-loners (200*0.1 = 20
# decay, 20 bump, +1 from passive at-camp tick = +1) while loners
# still drift to rogue (-80 + 20 + 1 = -59 per round trip → ~2 trips).
# Pre-fix social only refilled via the both-on-camp socialise action,
# which fired ~12 times in 1500 ticks — way too rare to counter decay.
DEPOSIT_SOCIAL_BUMP = 20.0
# Rest action heal bonus: resting while well-fed recovers health faster
# than the passive drip. Gives the rest branch a second purpose beyond
# energy recovery.
REST_HEAL_BONUS = 1.5
SOCIALISE_SOCIAL_RESTORE = 20.0

# One forage action consumes this many tile units. Paired with the
# 2–10 random food amounts per tile (see World._roll_resource), tiles
# now visibly decay across 1–5 serving badges in the UI as agents eat.
FORAGE_TILE_DEPLETION = 2.0

# Foragers keep surplus food in a pouch up to this cap. Once full, the
# forage guard idles — the agent has to head back to camp and deposit
# into colony.food_stock before they can pick up more. Creates a visible
# gather → carry → return loop that feeds the shared stockpile.
CARRY_MAX = 8.0

# Per-unit weight contributed to cargo by each resource type. Stone is
# heaviest, food lightest — so a stone-gathering trip ferries less mass
# than a food trip and triggers a faster return-to-camp. cargo_weight()
# below is the total — it's what CARRY_MAX is compared against.
FOOD_WEIGHT = 1.0
WOOD_WEIGHT = 2.0
STONE_WEIGHT = 3.0


def cargo_weight(agent):
    """Total weight of the agent's pouch in CARRY_MAX units.

    Three resource pouches → one weight number. Used by the cargo-full
    decision rung and by gather actions to size their take so a wood
    gather of 2 weight per unit can't push a near-full pouch over the
    cap. Pure: no I/O, derives from agent.cargo_food / cargo_wood /
    cargo_stone alone.
    """
    return (
        agent.cargo_food * FOOD_WEIGHT
        + agent.cargo_wood * WOOD_WEIGHT
        + agent.cargo_stone * STONE_WEIGHT
    )


def carry_max_for(colony):
    """Tier-scaled cargo cap for an agent of `colony`.

    The bare CARRY_MAX constant is the tier-0 baseline (8). Tier 1
    (Monastery) lifts to 12; tier 2 (Castle) to 16. Rogue agents
    (no colony) fall through to the baseline — they never benefit
    from infrastructure they're not part of.
    """
    return config.tier_benefit(colony, 'cargo_cap')

HEALTH_CRITICAL = 20.0
HUNGER_CRITICAL = 20.0
HUNGER_MODERATE = 50.0
ENERGY_CRITICAL = 15.0
SOCIAL_LOW = 30.0

NEED_MAX = 100.0


def apply_passive_social(agent, colony):
    """Add the at-camp passive social refill for a non-rogue agent.

    Called per tick alongside `decay_needs`. Pre-fix social only refilled
    via the `socialise` action, which required two agents on the camp
    tile simultaneously — a coincidence so rare that every agent
    eventually drifted to rogue. With this in place, an agent who
    actually returns home sees their social meter top up over time.

    Rogue agents are excluded by design: rogue is a one-way social
    collapse, going home doesn't reverse it.
    """
    if agent.rogue:
        return
    if not colony.is_at_camp(agent.x, agent.y):
        return
    agent.social = min(NEED_MAX, agent.social + PASSIVE_SOCIAL_AT_CAMP_RATE)


def decay_needs(agent, hunger_scale=1.0):
    agent.hunger = max(0.0, agent.hunger - HUNGER_DECAY * hunger_scale)
    agent.energy = max(0.0, agent.energy - ENERGY_DECAY)
    social_mult = LONER_SOCIAL_DECAY_MULT if agent.loner else 1.0
    agent.social = max(0.0, agent.social - SOCIAL_DECAY * social_mult)
    # Rogue flip: social collapsed to zero. One-way — even if the agent
    # later refills social (e.g. the user buffs it via a debug path), the
    # flag stays set. Models "you left the tribe too long, there's no
    # coming back."
    if agent.social <= 0.0 and not agent.rogue:
        agent.rogue = True
    if agent.hunger <= 0.0:
        agent.health = max(0.0, agent.health - STARVATION_HEALTH_DAMAGE)
    elif agent.hunger > HUNGER_MODERATE:
        agent.health = min(NEED_MAX, agent.health + PASSIVE_HEAL_RATE)
