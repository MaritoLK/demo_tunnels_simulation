"""Pure in-engine colony representation. No Flask, no DB.

Mirrors the `colonies` ORM row shape but lives in the engine layer so
agents can read colony state (camp position, food_stock, growing_count)
without reaching through the service. Mutations (food_stock++/-- and
growing_count++/--) happen here during a step; the service persists the
deltas via dirty-colony set after the step returns.
"""


class EngineColony:
    __slots__ = ('id', 'name', 'color', 'camp_x', 'camp_y',
                 'food_stock', 'growing_count', 'sprite_palette')

    def __init__(self, id, name, color, camp_x, camp_y,
                 food_stock, growing_count=0, sprite_palette='Blue'):
        self.id = id
        self.name = name
        self.color = color
        self.camp_x = camp_x
        self.camp_y = camp_y
        self.food_stock = food_stock
        self.growing_count = growing_count
        self.sprite_palette = sprite_palette

    def is_at_camp(self, x, y):
        return x == self.camp_x and y == self.camp_y

    def __repr__(self):
        return f"EngineColony(#{self.id} {self.name}/{self.sprite_palette} @({self.camp_x},{self.camp_y}))"
