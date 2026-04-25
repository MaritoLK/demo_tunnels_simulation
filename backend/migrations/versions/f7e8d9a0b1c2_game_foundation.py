"""game foundation: deleted scaffolding (no-op placeholder)

Revision ID: f7e8d9a0b1c2
Revises: e5f6a7b8c9da
Create Date: 2026-04-17 00:00:00.000000

Originally created six tables (npcs, relationships, event_log, policies,
save_meta, game_state) for an unshipped Tunnels Foundation feature. The
models, mappers, and tests were deleted on 2026-04-25; nothing in the
live engine/service/route path referenced them.

The migration file is preserved (not renamed/removed) to keep the
revision chain intact for environments that already applied it. Both
upgrade and downgrade are no-ops, so:
  * Fresh DBs skip table creation entirely.
  * Existing dev/test DBs retain the orphan tables until manually
    dropped — harmless because no live code references them.
"""


# revision identifiers, used by Alembic.
revision = 'f7e8d9a0b1c2'
down_revision = 'e5f6a7b8c9da'
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
