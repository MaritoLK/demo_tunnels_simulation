HUNGER_DECAY = 0.5
ENERGY_DECAY = 0.3
SOCIAL_DECAY = 0.1

STARVATION_HEALTH_DAMAGE = 2.0

FORAGE_HUNGER_RESTORE = 30.0
REST_ENERGY_RESTORE = 5.0
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
