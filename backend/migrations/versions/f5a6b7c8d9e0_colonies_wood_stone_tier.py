"""colonies: wood_stock, stone_stock, tier

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-04-26

Closes the wood/stone loose end. Forest and stone tiles already get
generated and rendered, but no agent action consumed them. Adds the
two new resource columns + a tier counter that the camp-upgrade
action increments.

All three columns default to 0 so existing colony rows stay valid
on rollout.
"""
from alembic import op
import sqlalchemy as sa


revision = 'f5a6b7c8d9e0'
down_revision = 'e4f5a6b7c8d9'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('colonies', sa.Column(
        'wood_stock', sa.Float(), nullable=False, server_default='0',
    ))
    op.add_column('colonies', sa.Column(
        'stone_stock', sa.Float(), nullable=False, server_default='0',
    ))
    op.add_column('colonies', sa.Column(
        'tier', sa.Integer(), nullable=False, server_default='0',
    ))


def downgrade():
    op.drop_column('colonies', 'tier')
    op.drop_column('colonies', 'stone_stock')
    op.drop_column('colonies', 'wood_stock')
