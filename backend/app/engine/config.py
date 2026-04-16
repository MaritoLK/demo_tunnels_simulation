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
