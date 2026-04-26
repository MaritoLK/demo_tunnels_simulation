"""agents.cargo column + colonies.food_stock Integer -> Float

Revision ID: e5f6a7b8c9da
Revises: d4e5f6a7b8c9
Create Date: 2026-04-17 00:00:00.000000

Two linked fixes:
  1. Agents carry a float pouch (engine: CARRY_MAX=8.0, FORAGE_TILE_DEPLETION=2.0).
     Pre-fix schema dropped the value on worker restart — foraged food vanished.
  2. food_stock was Integer while harvest/deposit/eat wrote floats.
     Postgres truncated/rejected fractional increments.

Upgrade is additive + a type widen with USING CAST; preserves existing stock values.
"""
from alembic import op
import sqlalchemy as sa


revision = 'e5f6a7b8c9da'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('agents', sa.Column(
        'cargo', sa.Float(), nullable=False, server_default='0.0',
    ))
    op.alter_column(
        'colonies', 'food_stock',
        existing_type=sa.Integer(),
        type_=sa.Float(),
        existing_nullable=False,
        existing_server_default='0',
        postgresql_using='food_stock::double precision',
    )


def downgrade():
    op.alter_column(
        'colonies', 'food_stock',
        existing_type=sa.Float(),
        type_=sa.Integer(),
        existing_nullable=False,
        existing_server_default='0',
        postgresql_using='food_stock::integer',
    )
    op.drop_column('agents', 'cargo')
