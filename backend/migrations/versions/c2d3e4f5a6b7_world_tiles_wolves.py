"""world_tiles.wolves column

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-04-26

Static hazard flag. World generation seeds wolves around high-food
tiles to bait risk/reward. Persisted per tile so a reload restores the
same hazard layout. Backfills to FALSE on existing rows — old worlds
become wolves-free (intentional: pre-fix demos were calibrated with no
hazards, retroactively adding them would change their balance).
"""
from alembic import op
import sqlalchemy as sa


revision = 'c2d3e4f5a6b7'
down_revision = 'b1c2d3e4f5a6'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('world_tiles', sa.Column(
        'wolves', sa.Boolean(), nullable=False, server_default=sa.false(),
    ))


def downgrade():
    op.drop_column('world_tiles', 'wolves')
