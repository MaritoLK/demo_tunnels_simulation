"""agents.tiles_walked column

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-04-26

Lifetime tile-step counter per agent. Drives the walk-skill tier
table that scales fog reveal radius (apprentice 3x3 → journeyman 5x5
→ veteran 7x7). Persisted so a reload preserves earned sight; in-
memory defaults to 0 so existing rows retroactively start as
apprentices (consistent with the engine's pre-existing behavior).
"""
from alembic import op
import sqlalchemy as sa


revision = 'd3e4f5a6b7c8'
down_revision = 'c2d3e4f5a6b7'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('agents', sa.Column(
        'tiles_walked', sa.Integer(), nullable=False, server_default='0',
    ))


def downgrade():
    op.drop_column('agents', 'tiles_walked')
