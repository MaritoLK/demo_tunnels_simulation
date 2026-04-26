"""World grid, Tile, and procedural generation. Pure Python — no Flask, no DB."""
import random

from . import config


TERRAINS = ('grass', 'water', 'forest', 'stone', 'sand')

TERRAIN_WEIGHTS = {
    'grass': 60,
    'forest': 15,
    'water': 10,
    'stone': 10,
    'sand': 5,
}

# Voronoi biome seeds. Per-tile weighted RNG produces salt-and-pepper
# noise where every terrain is a 1×1 cell. CA smoothing (majority vote
# in a 3×3 neighbourhood) can't fix that here because grass at 60%
# weight dominates every non-grass cell's neighbourhood — the smoother
# reinforces the dominant terrain instead of clustering minorities.
#
# Voronoi is the right tool: scatter N "biome seeds" over the grid,
# each seed tagged with a terrain drawn from the same weighted
# distribution. Every tile takes the terrain of the *nearest* seed.
# Result: contiguous biomes at any weight ratio — 15% forest produces
# actual forest patches, not single trees scattered across grass.
#
# Seeds per tile: BIOME_SEEDS_PER_TILE controls biome granularity.
# 0.04 = ~40 seeds on a 40×25 = 1000-tile world, so average biome
# is ~25 tiles. Feels right for demo scale: big enough to recognise
# as a "forest" or "lake", small enough that 40×25 holds several.
BIOME_SEEDS_PER_TILE = 0.04
MIN_BIOME_SEEDS = 6  # floor for tiny worlds so even 4×4 gets variety

# Tightened from 0.12 → 0.06 in the fog-of-war pass: fewer food tiles
# per grass field so a colony can't survive on tiles within sight of
# their camp. Drives agents to clear fog and discover food beyond their
# immediate vicinity. Pair with the lowered per-tile range below — both
# knobs together cut total starting food roughly to a third.
FOOD_ON_GRASS_CHANCE = 0.06
INITIAL_RESOURCE_AMOUNT = {
    'food': 10.0,
    'wood': 15.0,
    'stone': 10.0,
}
# Per-food-tile yield range. Was (2, 10) avg 6; lowered to (1, 5) avg 3
# so a single tile feeds fewer forages and the colony has to keep moving.
FOOD_TILE_YIELD_MIN = 1
FOOD_TILE_YIELD_MAX = 5


class Tile:
    __slots__ = (
        'x', 'y', 'terrain', 'resource_type', 'resource_amount',
        'crop_state', 'crop_growth_ticks', 'crop_colony_id',
    )

    def __init__(self, x, y, terrain, resource_type=None, resource_amount=0.0,
                 crop_state='none', crop_growth_ticks=0, crop_colony_id=None):
        self.x = x
        self.y = y
        self.terrain = terrain
        self.resource_type = resource_type
        self.resource_amount = resource_amount
        self.crop_state = crop_state
        self.crop_growth_ticks = crop_growth_ticks
        self.crop_colony_id = crop_colony_id

    @property
    def is_walkable(self):
        return self.terrain != 'water'

    def __repr__(self):
        return f"Tile({self.x},{self.y},{self.terrain})"


class World:
    def __init__(self, width, height):
        self.width = width
        self.height = height

    def generate(self, seed=None):
        rng = random.Random(seed)
        terrains = list(TERRAIN_WEIGHTS.keys())
        weights = list(TERRAIN_WEIGHTS.values())

        # Phase 1 — scatter biome seeds. Each seed is (sx, sy, terrain).
        # Seed count scales with world area so biome size stays roughly
        # constant across grid dimensions. Floor at MIN_BIOME_SEEDS so
        # small worlds still get terrain variety.
        n_seeds = max(MIN_BIOME_SEEDS, int(self.width * self.height * BIOME_SEEDS_PER_TILE))
        seeds = []
        for _ in range(n_seeds):
            sx = rng.randint(0, self.width - 1)
            sy = rng.randint(0, self.height - 1)
            terrain = rng.choices(terrains, weights=weights, k=1)[0]
            seeds.append((sx, sy, terrain))

        # Phase 2 — every tile takes the terrain of its nearest seed
        # (squared Euclidean distance; sqrt is monotonic so skip it).
        # Ties go to the first-found seed, which is deterministic given
        # the seeds list order.
        self.tiles = []
        for y in range(self.height):
            row = []
            for x in range(self.width):
                best_dist = None
                best_terrain = seeds[0][2]
                for sx, sy, terrain in seeds:
                    dx = sx - x
                    dy = sy - y
                    d = dx * dx + dy * dy
                    if best_dist is None or d < best_dist:
                        best_dist = d
                        best_terrain = terrain
                resource_type, resource_amount = self._roll_resource(best_terrain, rng)
                row.append(Tile(x, y, best_terrain, resource_type, resource_amount))
            self.tiles.append(row)

        # Invariant: at least one walkable tile. If every seed rolled
        # water, the whole map is water. Force (0,0) to grass
        # deterministically rather than retry with a perturbed seed
        # (which would break the seed→state contract).
        if not any(t.is_walkable for row in self.tiles for t in row):
            fallback = self.tiles[0][0]
            fallback.terrain = 'grass'
            fallback.resource_type = None
            fallback.resource_amount = 0.0

    @staticmethod
    def _roll_resource(terrain, rng):
        if terrain == 'grass' and rng.random() < FOOD_ON_GRASS_CHANCE:
            # Food is variable per tile so the 'x N' badge shows actual
            # depletion rather than a flat starting value. Range was
            # widened (2-10) before the scarcity pass; tightened to
            # FOOD_TILE_YIELD_{MIN,MAX} (1-5) so a colony can't sit on
            # one tile through the early game.
            return 'food', float(rng.randint(FOOD_TILE_YIELD_MIN, FOOD_TILE_YIELD_MAX))
        if terrain == 'forest':
            return 'wood', INITIAL_RESOURCE_AMOUNT['wood']
        if terrain == 'stone':
            return 'stone', INITIAL_RESOURCE_AMOUNT['stone']
        return None, 0.0

    def get_tile(self, x, y):
        return self.tiles[y][x]

    def in_bounds(self, x, y):
        return 0 <= x < self.width and 0 <= y < self.height

    def find_nearest_tile(self, x, y, predicate):
        best = None
        best_dist = None
        for row in self.tiles:
            for tile in row:
                if not predicate(tile):
                    continue
                d = abs(tile.x - x) + abs(tile.y - y)
                if best_dist is None or d < best_dist:
                    best = tile
                    best_dist = d
        return best

    def tick(self, phase):
        """World-level per-tick logic. Currently: crop growth (day phase only).

        Returns a list of event dicts (e.g. `crop_matured`) emitted this
        tick. Pure: no I/O, deterministic given tile state + phase.
        """
        if phase != 'day':
            return []
        events = []
        for row in self.tiles:
            for tile in row:
                if tile.crop_state != 'growing':
                    continue
                tile.crop_growth_ticks += 1
                if tile.crop_growth_ticks >= config.CROP_MATURE_TICKS:
                    tile.crop_state = 'mature'
                    tile.resource_amount = config.HARVEST_YIELD
                    events.append({
                        'type': 'crop_matured',
                        'description': f'crop matured at ({tile.x},{tile.y})',
                        'data': {
                            'tile_x': tile.x,
                            'tile_y': tile.y,
                            'colony_id': tile.crop_colony_id,
                        },
                    })
        return events
