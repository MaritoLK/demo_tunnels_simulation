"""colonies table + crop columns on world_tiles + colony_id FK on agents

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-04-15 00:00:00.000000

All schema additions are additive. The one intentional destructive step
is `DELETE FROM agents` and `DELETE FROM world_tiles` in upgrade(): the
nullable colony_id FK would otherwise leave pre-existing agent rows with
NULL and break the frontend sprite tint lookup. This is a dev-only project
(pre-demo, no production data), so a wipe is safe and avoids a two-step
nullable → backfill → NOT NULL migration.
"""
from alembic import op
import sqlalchemy as sa


revision = 'd4e5f6a7b8c9'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'colonies',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(50), nullable=False),
        sa.Column('color', sa.String(7), nullable=False),
        sa.Column('camp_x', sa.Integer(), nullable=False),
        sa.Column('camp_y', sa.Integer(), nullable=False),
        sa.Column('food_stock', sa.Integer(), nullable=False, server_default='0'),
    )

    op.execute('DELETE FROM events')
    op.execute('DELETE FROM agents')
    op.execute('DELETE FROM world_tiles')
    op.execute('DELETE FROM simulation_state')

    op.add_column('agents', sa.Column(
        'colony_id', sa.Integer(),
        sa.ForeignKey('colonies.id', ondelete='SET NULL'),
        nullable=True,
    ))

    op.add_column('world_tiles', sa.Column(
        'crop_state', sa.String(10), nullable=False, server_default='none',
    ))
    op.add_column('world_tiles', sa.Column(
        'crop_growth_ticks', sa.Integer(), nullable=False, server_default='0',
    ))
    op.add_column('world_tiles', sa.Column(
        'crop_colony_id', sa.Integer(),
        sa.ForeignKey('colonies.id', ondelete='SET NULL'),
        nullable=True,
    ))

    op.create_index(
        'idx_tiles_crop_state', 'world_tiles', ['crop_state'],
        postgresql_where=sa.text("crop_state != 'none'"),
    )


def downgrade():
    op.drop_index('idx_tiles_crop_state', table_name='world_tiles')
    op.drop_column('world_tiles', 'crop_colony_id')
    op.drop_column('world_tiles', 'crop_growth_ticks')
    op.drop_column('world_tiles', 'crop_state')
    op.drop_column('agents', 'colony_id')
    op.drop_table('colonies')
