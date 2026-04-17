"""Need-tuning constants and the per-tick decay function. Pure Python."""
HUNGER_DECAY = 0.5
ENERGY_DECAY = 0.3
SOCIAL_DECAY = 0.1

# Night-phase hunger scaling: agents decay slower while sleeping. Applied
# in tick_agent via cycle.phase_for; keeps the constant here so needs.py
# remains the single home for all decay-related tuning.
NIGHT_HUNGER_SCALE = 0.5

# Loner: promoted at spawn (see simulation.new_simulation). Their social
# need decays at this multiple of SOCIAL_DECAY, so rogue transitions
# happen inside a short demo window. Tuned so a loner reaches
# SOCIAL_LOW (30) in ~60 default-speed ticks and rogue (0) in ~250 —
# both comfortably within a 5-minute demo at 1×.
LONER_SOCIAL_DECAY_MULT = 4.0

STARVATION_HEALTH_DAMAGE = 2.0

# Passive health regen: a well-fed agent slowly recovers. Without this,
# any agent that ever starves stays damaged forever — the "zombie" state
# where health is below max but never moves. Symmetric with the starvation
# damage branch: decay_needs is the one place health changes each tick.
PASSIVE_HEAL_RATE = 0.3

FORAGE_HUNGER_RESTORE = 20.0
REST_ENERGY_RESTORE = 5.0
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

HEALTH_CRITICAL = 20.0
HUNGER_CRITICAL = 20.0
HUNGER_MODERATE = 50.0
ENERGY_CRITICAL = 15.0
SOCIAL_LOW = 30.0

NEED_MAX = 100.0


def decay_needs(agent, hunger_scale=1.0):
    agent.hunger = max(0.0, agent.hunger - HUNGER_DECAY * hunger_scale)
    agent.energy = max(0.0, agent.energy - ENERGY_DECAY)
    social_mult = LONER_SOCIAL_DECAY_MULT if getattr(agent, 'loner', False) else 1.0
    agent.social = max(0.0, agent.social - SOCIAL_DECAY * social_mult)
    # Rogue flip: social collapsed to zero. One-way — even if the agent
    # later refills social (e.g. the user buffs it via a debug path), the
    # flag stays set. Models "you left the tribe too long, there's no
    # coming back." Gated by `getattr` so legacy callers with bare Agent
    # stand-ins (pre-slot) don't NPE; production Agent always has it.
    if agent.social <= 0.0 and not getattr(agent, 'rogue', False):
        agent.rogue = True
    if agent.hunger <= 0.0:
        agent.health = max(0.0, agent.health - STARVATION_HEALTH_DAMAGE)
    elif agent.hunger > HUNGER_MODERATE:
        agent.health = min(NEED_MAX, agent.health + PASSIVE_HEAL_RATE)
