"""agents.rogue + agents.loner columns

Revision ID: b1c2d3e4f5a6
Revises: a0b1c2d3e4f5
Create Date: 2026-04-26

Both flags lived only in the engine's in-memory Agent until now. The
service-layer mapper round-trip silently dropped them, so a worker
restart re-rolled rogue back to False (engine invariant: "no redemption
arc") and loner back to False (re-bucketed the demo's social-decay
calibration). Adds the columns with NOT NULL + server_default('false')
so existing rows backfill to the correct engine default without an
explicit UPDATE pass.
"""
from alembic import op
import sqlalchemy as sa


revision = 'b1c2d3e4f5a6'
down_revision = 'a0b1c2d3e4f5'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('agents', sa.Column(
        'rogue', sa.Boolean(), nullable=False, server_default=sa.false(),
    ))
    op.add_column('agents', sa.Column(
        'loner', sa.Boolean(), nullable=False, server_default=sa.false(),
    ))


def downgrade():
    op.drop_column('agents', 'loner')
    op.drop_column('agents', 'rogue')
