"""simulation_state: persist seed + RNG sub-stream state for honest reload

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-04-12 23:30:00.000000

Three nullable columns on simulation_state so a cold reload can
rehydrate the sim with its full RNG trajectory intact:

  * seed           — master seed for the sim (informational; RNG state
                     columns are what actually drive reproducibility)
  * rng_spawn_state — JSONB snapshot of Simulation.rng_spawn.getstate()
  * rng_tick_state  — JSONB snapshot of Simulation.rng_tick.getstate()

`random.Random.getstate()` returns (version, tuple-of-625-ints, gauss_next).
We convert the inner tuple → list for JSONB round-tripping and reverse on
load. Skipping this (re-seeding from master on reload) would mean tick N
after reload diverges from tick N in the original continuous run.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('simulation_state', sa.Column('seed', sa.BigInteger(), nullable=True))
    op.add_column('simulation_state', sa.Column('rng_spawn_state', JSONB, nullable=True))
    op.add_column('simulation_state', sa.Column('rng_tick_state', JSONB, nullable=True))


def downgrade():
    op.drop_column('simulation_state', 'rng_tick_state')
    op.drop_column('simulation_state', 'rng_spawn_state')
    op.drop_column('simulation_state', 'seed')
