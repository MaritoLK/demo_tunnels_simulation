from app import db


class Relationship(db.Model):
    """Directed-but-canonicalised pair link between two NPCs.

    Invariant: `npc_a_id < npc_b_id` (enforced by CHECK `rel_canonical_order`)
    so a pair has exactly one row regardless of which side was created first.
    The `(npc_a_id, npc_b_id, type)` triple is UNIQUE to prevent duplicates
    while still allowing two NPCs to carry multiple relationship types
    (e.g. 'spouse' + 'councilor').
    """

    __tablename__ = 'relationships'

    id = db.Column(db.Integer, primary_key=True)
    npc_a_id = db.Column(
        db.Integer,
        db.ForeignKey('npcs.id', ondelete='CASCADE'),
        nullable=False,
    )
    npc_b_id = db.Column(
        db.Integer,
        db.ForeignKey('npcs.id', ondelete='CASCADE'),
        nullable=False,
    )
    type = db.Column(db.String(16), nullable=False)  # 'spouse', 'rival', 'councilor', ...
    strength = db.Column(
        db.SmallInteger, nullable=False, default=0, server_default='0',
    )

    __table_args__ = (
        db.CheckConstraint('npc_a_id < npc_b_id', name='rel_canonical_order'),
        db.UniqueConstraint(
            'npc_a_id', 'npc_b_id', 'type', name='uq_relationship_pair_type',
        ),
        db.Index('idx_rel_a', 'npc_a_id'),
        db.Index('idx_rel_b', 'npc_b_id'),
    )


def _canonical_pair(a: int, b: int) -> tuple[int, int]:
    """Return (a, b) ordered so the smaller id is first.

    Invariant helper matching the `rel_canonical_order` CHECK constraint:
    every Relationship row stores its endpoints with `npc_a_id < npc_b_id`,
    so writers must canonicalise before construction. Task 2's mappers use
    this helper.
    """
    return (a, b) if a < b else (b, a)
