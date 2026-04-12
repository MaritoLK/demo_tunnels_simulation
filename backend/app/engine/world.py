"""World grid, Tile, and procedural generation. Pure Python — no Flask, no DB."""
import random


TERRAINS = ('grass', 'water', 'forest', 'stone', 'sand')

TERRAIN_WEIGHTS = {
    'grass': 60,
    'forest': 15,
    'water': 10,
    'stone': 10,
    'sand': 5,
}

FOOD_ON_GRASS_CHANCE = 0.30
INITIAL_RESOURCE_AMOUNT = {
    'food': 20.0,
    'wood': 15.0,
    'stone': 10.0,
}


class Tile:
    __slots__ = ('x', 'y', 'terrain', 'resource_type', 'resource_amount')

    def __init__(self, x, y, terrain, resource_type=None, resource_amount=0.0):
        self.x = x
        self.y = y
        self.terrain = terrain
        self.resource_type = resource_type
        self.resource_amount = resource_amount

    @property
    def is_walkable(self):
        return self.terrain != 'water'

    def __repr__(self):
        return f"Tile({self.x},{self.y},{self.terrain})"


class World:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.tiles = []

    def generate(self, seed=None):
        rng = random.Random(seed)
        terrains = list(TERRAIN_WEIGHTS.keys())
        weights = list(TERRAIN_WEIGHTS.values())

        self.tiles = []
        for y in range(self.height):
            row = []
            for x in range(self.width):
                terrain = rng.choices(terrains, weights=weights, k=1)[0]
                resource_type, resource_amount = self._roll_resource(terrain, rng)
                row.append(Tile(x, y, terrain, resource_type, resource_amount))
            self.tiles.append(row)

        # Invariant: at least one walkable tile. Unlucky seeds on small grids
        # can roll every tile to water. Force (0,0) to grass deterministically
        # rather than retry with a perturbed seed (which would break the
        # seed→state contract).
        if not any(t.is_walkable for row in self.tiles for t in row):
            fallback = self.tiles[0][0]
            fallback.terrain = 'grass'
            fallback.resource_type = None
            fallback.resource_amount = 0.0

    @staticmethod
    def _roll_resource(terrain, rng):
        if terrain == 'grass' and rng.random() < FOOD_ON_GRASS_CHANCE:
            return 'food', INITIAL_RESOURCE_AMOUNT['food']
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
