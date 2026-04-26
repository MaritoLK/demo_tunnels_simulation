"""Walk-skill tier table.

The fog reveal radius scales with how many tiles an agent has actually
moved through during their lifetime. Newcomers see a 3x3 block; trained
scouts see 5x5; veterans see 7x7. Single source of truth — both the
simulation's reveal pass and any future UI panel pull from this table.
"""

# (tiles_walked threshold, reveal radius). Sorted ascending. The
# threshold is the MINIMUM tiles_walked at which that radius applies.
WALK_SKILL_TIERS = (
    (0,   1),   # apprentice: 3x3
    (50,  2),   # journeyman: 5x5
    (150, 3),   # veteran:    7x7
)


def reveal_radius_for(tiles_walked):
    """Return the reveal radius for an agent who has walked this many
    tiles. Increasing — never shrinks — and bounded by the table's
    last entry."""
    radius = WALK_SKILL_TIERS[0][1]
    for threshold, r in WALK_SKILL_TIERS:
        if tiles_walked >= threshold:
            radius = r
        else:
            break
    return radius


def tier_for(tiles_walked):
    """Index into WALK_SKILL_TIERS. Useful for UI labels (apprentice /
    journeyman / veteran)."""
    tier = 0
    for i, (threshold, _r) in enumerate(WALK_SKILL_TIERS):
        if tiles_walked >= threshold:
            tier = i
        else:
            break
    return tier
