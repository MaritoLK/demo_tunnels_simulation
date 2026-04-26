"""colony sprite_palette column

Revision ID: a0b1c2d3e4f5
Revises: f7e8d9a0b1c2
Create Date: 2026-04-23

"""
from alembic import op
import sqlalchemy as sa


revision = 'a0b1c2d3e4f5'
down_revision = 'f7e8d9a0b1c2'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'colonies',
        sa.Column(
            'sprite_palette',
            sa.String(length=16),
            nullable=False,
            server_default='Blue',
        ),
    )
    # Explicit backfill for rows whose name matches the DEFAULT_COLONY_PALETTE.
    # Rows with any other name keep the 'Blue' server_default. No demo data
    # hits the else branch today; the explicit IN list prevents future
    # non-palette colonies from silently becoming Blue without notice.
    op.execute(
        "UPDATE colonies SET sprite_palette = name "
        "WHERE name IN ('Red', 'Blue', 'Purple', 'Yellow')"
    )


def downgrade():
    op.drop_column('colonies', 'sprite_palette')
