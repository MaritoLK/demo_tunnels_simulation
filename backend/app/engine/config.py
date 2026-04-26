"""Tunable balance constants for day/night + cultivation.

See docs/superpowers/specs/2026-04-15-day-night-cultivation-design.md
§"Balance parameters" for derivation. Changing these values shifts the
demo's "who survives by day 5" dynamic — manual calibration required
after any edit.
"""
HARVEST_YIELD = 9
INITIAL_FOOD_STOCK = 18
EAT_COST = 6
CROP_MATURE_TICKS = 60
WILD_RESOURCE_MAX = 5
WILD_TILE_DENSITY = 0.15
MAX_FIELDS_PER_COLONY = 4

# Fog of war reveal radius (Chebyshev — square ring around the agent).
# 1 = the 3x3 block centred on the agent. Future: scaled by walking-skill
# tier so veteran scouts uncover wider areas.
REVEAL_RADIUS = 1

# How many recent productive forage tiles each agent remembers. The
# explore branch biases toward these so "all needs ok → wander" becomes
# "all needs ok → patrol known caches." 3 is small enough that the
# memory turns over within a few days, big enough that a single
# depleted tile doesn't strand the agent.
FOOD_MEMORY_MAX = 3

# Crops are clustered into a square (Chebyshev) field around the colony's
# camp instead of speckling the world. 4 = a 9x9 area centered on camp,
# minus the camp tile itself (where the house sprite renders). Tunable:
# bump for more crop real estate, drop for tighter agriculture. Pre-fix
# agents planted anywhere they hit empty grass, including ON the camp
# sprite — visually noisy and made fields impossible to read at a glance.
PLANT_RADIUS_FROM_CAMP = 4
