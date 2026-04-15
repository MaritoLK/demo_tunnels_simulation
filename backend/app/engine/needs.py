"""Need-tuning constants and the per-tick decay function. Pure Python."""
HUNGER_DECAY = 0.5
ENERGY_DECAY = 0.3
SOCIAL_DECAY = 0.1

# Night-phase hunger scaling: agents decay slower while sleeping. Applied
# in tick_agent via cycle.phase_for; keeps the constant here so needs.py
# remains the single home for all decay-related tuning.
NIGHT_HUNGER_SCALE = 0.5

STARVATION_HEALTH_DAMAGE = 2.0

# Passive health regen: a well-fed agent slowly recovers. Without this,
# any agent that ever starves stays damaged forever — the "zombie" state
# where health is below max but never moves. Symmetric with the starvation
# damage branch: decay_needs is the one place health changes each tick.
PASSIVE_HEAL_RATE = 0.3

FORAGE_HUNGER_RESTORE = 30.0
REST_ENERGY_RESTORE = 5.0
# Rest action heal bonus: resting while well-fed recovers health faster
# than the passive drip. Gives the rest branch a second purpose beyond
# energy recovery.
REST_HEAL_BONUS = 1.5
SOCIALISE_SOCIAL_RESTORE = 20.0

FORAGE_TILE_DEPLETION = 5.0

HEALTH_CRITICAL = 20.0
HUNGER_CRITICAL = 20.0
HUNGER_MODERATE = 50.0
ENERGY_CRITICAL = 15.0
SOCIAL_LOW = 30.0

NEED_MAX = 100.0


def decay_needs(agent):
    agent.hunger = max(0.0, agent.hunger - HUNGER_DECAY)
    agent.energy = max(0.0, agent.energy - ENERGY_DECAY)
    agent.social = max(0.0, agent.social - SOCIAL_DECAY)
    if agent.hunger <= 0.0:
        agent.health = max(0.0, agent.health - STARVATION_HEALTH_DAMAGE)
    elif agent.hunger > HUNGER_MODERATE:
        agent.health = min(NEED_MAX, agent.health + PASSIVE_HEAL_RATE)
