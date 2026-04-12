"""events: composite (agent_id, tick) index, tighten FK to RESTRICT

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-12 22:30:00.000000

Two events-table fixes bundled into one migration:

  * Drop idx_events_agent_id; add idx_events_agent_tick (agent_id, tick).
    Dominant read pattern is "timeline for agent N" — WHERE agent_id = ?
    ORDER BY tick. A composite serves filter + order from one index scan.
    The composite's leading prefix also covers bare agent_id lookups, so
    the standalone index is redundant.

  * events.agent_id FK: ON DELETE SET NULL → ON DELETE RESTRICT. Agents
    are soft-deleted via alive=false and are never supposed to be hard-
    deleted. The SET NULL cascade was defensive cruft that, if ever
    triggered, would silently erase historical event attribution.
"""
from alembic import op


revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_index('idx_events_agent_id', table_name='events')
    op.create_index(
        'idx_events_agent_tick',
        'events',
        ['agent_id', 'tick'],
        unique=False,
    )

    op.drop_constraint('events_agent_id_fkey', 'events', type_='foreignkey')
    op.create_foreign_key(
        'events_agent_id_fkey',
        'events',
        'agents',
        ['agent_id'],
        ['id'],
        ondelete='RESTRICT',
    )


def downgrade():
    op.drop_constraint('events_agent_id_fkey', 'events', type_='foreignkey')
    op.create_foreign_key(
        'events_agent_id_fkey',
        'events',
        'agents',
        ['agent_id'],
        ['id'],
        ondelete='SET NULL',
    )

    op.drop_index('idx_events_agent_tick', table_name='events')
    op.create_index(
        'idx_events_agent_id',
        'events',
        ['agent_id'],
        unique=False,
    )
