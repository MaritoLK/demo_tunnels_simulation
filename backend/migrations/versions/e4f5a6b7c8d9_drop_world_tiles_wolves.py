"""drop world_tiles.wolves

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-04-26

The wolves hazard was added in c2d3e4f5a6b7 and removed in this revision.
The mechanic didn't pull its weight in the demo loop — agents either
avoided the high-yield clusters entirely or took a single bite and
recovered, neither of which made the risk/reward shape readable. Drop
the column so the schema matches the engine state.

Downgrade re-adds the column with the same default as the introducing
migration (FALSE), so a roll-back leaves existing rows in the same
shape they had immediately after c2d3e4f5a6b7 ran.
"""
from alembic import op
import sqlalchemy as sa


revision = 'e4f5a6b7c8d9'
down_revision = 'd3e4f5a6b7c8'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_column('world_tiles', 'wolves')


def downgrade():
    op.add_column('world_tiles', sa.Column(
        'wolves', sa.Boolean(), nullable=False, server_default=sa.false(),
    ))
