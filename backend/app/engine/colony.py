"""Pure in-engine colony representation. No Flask, no DB.

Mirrors the `colonies` ORM row shape but lives in the engine layer so
agents can read colony state (camp position, food_stock, growing_count)
without reaching through the service. Mutations (food_stock++/-- and
growing_count++/--) happen here during a step; the service persists the
deltas via dirty-colony set after the step returns.
"""


class EngineColony:
    __slots__ = ('id', 'name', 'color', 'camp_x', 'camp_y',
                 'food_stock', 'growing_count', 'sprite_palette',
                 'explored', 'last_reproduction_tick', 'agent_name_counter',
                 'wood_stock', 'stone_stock', 'tier')

    def __init__(self, id, name, color, camp_x, camp_y,
                 food_stock, growing_count=0, sprite_palette='Blue',
                 wood_stock=0, stone_stock=0, tier=0):
        self.id = id
        self.name = name
        self.color = color
        self.camp_x = camp_x
        self.camp_y = camp_y
        self.food_stock = food_stock
        self.growing_count = growing_count
        self.sprite_palette = sprite_palette
        # Wood / stone stockpiles. Forest tiles drop wood, stone tiles
        # drop stone — both via the gather_wood / gather_stone actions
        # which deposit straight to the colony stock (no per-agent
        # cargo transport for the demo: agents act as lumberjacks /
        # miners delivering directly home). Spent on camp tier upgrades.
        self.wood_stock = wood_stock
        self.stone_stock = stone_stock
        # Camp tier: 0 = founders' shack, increments via upgrade_camp.
        # Each tier swaps the house sprite (House1 → House2 → House3)
        # and bumps the per-agent fog reveal radius by +tier.
        self.tier = tier
        # Cumulative set of (x, y) tiles this colony has revealed.
        # Refilled per tick from each non-rogue agent's reveal radius.
        # In-memory only — demo restarts naturally re-fog the map.
        self.explored = set()
        # Tick of the last successful dawn-meal reproduction, or None
        # if no birth yet. Drives the REPRODUCTION_COOLDOWN_TICKS gate
        # in Simulation._maybe_reproduce. In-memory only for the demo;
        # restart re-arms reproduction immediately, which is fine.
        self.last_reproduction_tick = None
        # Monotonic counter for naming new agents born to this colony.
        # Pre-fix the spawn used `f'{name}-{pop + 1}'` (current alive
        # count) — when an agent died and another was born, the new one
        # could re-use a dead agent's name. Using a never-decrementing
        # counter prevents that. Bumped here on birth; the suffix
        # equals counter at time of birth so names read 'Red-1, Red-2,
        # Red-N...'.
        self.agent_name_counter = 0

    def is_at_camp(self, x, y):
        return x == self.camp_x and y == self.camp_y

    def __repr__(self):
        return f"EngineColony(#{self.id} {self.name}/{self.sprite_palette} @({self.camp_x},{self.camp_y}))"
