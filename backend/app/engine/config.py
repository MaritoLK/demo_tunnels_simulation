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
# camp. The plantable area is the ring between PLANT_NO_BUILD_RADIUS and
# PLANT_RADIUS_FROM_CAMP — i.e. far enough out that the oversized house
# sprite (2 tiles wide × 3 tall, anchored to the camp tile and growing
# upward) doesn't overlap any crops, but close enough to read as the
# colony's field. With NO_BUILD=2 and FIELD=4 you get a 5×5 reserved
# centre for the house + halo and a 9×9 - 5×5 = 56-tile plantable ring.
PLANT_NO_BUILD_RADIUS = 2
PLANT_RADIUS_FROM_CAMP = 4

# Reproduction (dawn-meal ritual). Triggered in simulation.step at dawn
# when:
#   * food_stock >= REPRODUCTION_FOOD_THRESHOLD (the colony has slack
#     to feed a new mouth)
#   * cooldown REPRODUCTION_COOLDOWN_TICKS has elapsed since last birth
#   * population < MAX_AGENTS_PER_COLONY
#   * at least one alive non-rogue colony agent stands on the camp tile
#     (the 'midwife' — without it the trigger would fire even when
#     everyone is in the field)
# Cost: REPRODUCTION_FOOD_COST debited from food_stock. Pre-tuning for
# a 5-min demo (1500 ticks ≈ 12.5 days): cooldown of ~2 days = 6 births
# per colony per demo. Pop cap stops runaway growth.
REPRODUCTION_FOOD_THRESHOLD = 30
REPRODUCTION_FOOD_COST = 10
REPRODUCTION_COOLDOWN_TICKS = 240
MAX_AGENTS_PER_COLONY = 12

# Natural death by old age. Checked in tick_agent before the need-decay
# pass so age-out and starvation deaths can't fight for the same tick
# — the cause field discriminates them. 1800 ticks ≈ 15 in-game days
# at TICKS_PER_DAY=120, so a freshly-born agent lives roughly the
# duration of a long demo before timing out. Tunable: shorter for more
# generational churn, longer for stable populations.
MAX_AGE_TICKS = 1800
