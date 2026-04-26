"""agents: rename cargo → cargo_food, add cargo_wood / cargo_stone

Revision ID: a6b7c8d9e0f1
Revises: f5a6b7c8d9e0
Create Date: 2026-04-26

Multi-resource cargo refactor. Pre-migration each agent had a single
`cargo` float that held food units only; gather_wood / gather_stone
bypassed the agent and went straight into the colony stocks. The
new model unifies the gather → carry → deposit loop across all three
resources. Weight differs per resource (food=1, wood=2, stone=3) so
the cap (needs.CARRY_MAX) bites stone trips the hardest.

The data move is a 1:1 rename of `cargo` → `cargo_food`; the two new
columns default to 0 so any existing pouch is interpreted as
"food-only." Downgrade reverses by collapsing cargo_food back to
cargo and dropping the wood/stone columns.
"""
from alembic import op
import sqlalchemy as sa


revision = 'a6b7c8d9e0f1'
down_revision = 'f5a6b7c8d9e0'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('agents', 'cargo', new_column_name='cargo_food')
    op.add_column('agents', sa.Column(
        'cargo_wood', sa.Float(), nullable=False, server_default='0.0',
    ))
    op.add_column('agents', sa.Column(
        'cargo_stone', sa.Float(), nullable=False, server_default='0.0',
    ))


def downgrade():
    op.drop_column('agents', 'cargo_stone')
    op.drop_column('agents', 'cargo_wood')
    op.alter_column('agents', 'cargo_food', new_column_name='cargo')
