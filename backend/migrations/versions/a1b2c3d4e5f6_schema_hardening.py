"""schema hardening: drop low-cardinality event_type index, timestamptz on
all created_at / updated_at, NOT NULL on those columns, singleton constraint
on simulation_state.

Revision ID: a1b2c3d4e5f6
Revises: 37a96d923058
Create Date: 2026-04-12 21:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'a1b2c3d4e5f6'
down_revision = '37a96d923058'
branch_labels = None
depends_on = None


def upgrade():
    # DB#4 — drop idx_events_event_type (6-cardinality string col, no query path uses it)
    op.drop_index('idx_events_event_type', table_name='events')

    # DB#6 — timestamptz + NOT NULL on every auto-populated timestamp col.
    #   USING <col> AT TIME ZONE 'UTC' preserves existing naive timestamps as UTC.
    op.execute(
        "ALTER TABLE agents "
        "ALTER COLUMN created_at TYPE TIMESTAMP WITH TIME ZONE "
        "USING created_at AT TIME ZONE 'UTC', "
        "ALTER COLUMN created_at SET NOT NULL"
    )
    op.execute(
        "ALTER TABLE events "
        "ALTER COLUMN created_at TYPE TIMESTAMP WITH TIME ZONE "
        "USING created_at AT TIME ZONE 'UTC', "
        "ALTER COLUMN created_at SET NOT NULL"
    )
    op.execute(
        "ALTER TABLE simulation_state "
        "ALTER COLUMN created_at TYPE TIMESTAMP WITH TIME ZONE "
        "USING created_at AT TIME ZONE 'UTC', "
        "ALTER COLUMN created_at SET NOT NULL, "
        "ALTER COLUMN updated_at TYPE TIMESTAMP WITH TIME ZONE "
        "USING updated_at AT TIME ZONE 'UTC', "
        "ALTER COLUMN updated_at SET NOT NULL"
    )

    # DB#5 — singleton constraint on simulation_state.
    #   Indexing a constant expression caps the table at exactly one row:
    #   every row indexes the same value, so the unique constraint rejects #2.
    op.execute(
        "CREATE UNIQUE INDEX uq_simulation_state_singleton "
        "ON simulation_state ((true))"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS uq_simulation_state_singleton")

    op.execute(
        "ALTER TABLE simulation_state "
        "ALTER COLUMN updated_at DROP NOT NULL, "
        "ALTER COLUMN updated_at TYPE TIMESTAMP WITHOUT TIME ZONE "
        "USING updated_at AT TIME ZONE 'UTC', "
        "ALTER COLUMN created_at DROP NOT NULL, "
        "ALTER COLUMN created_at TYPE TIMESTAMP WITHOUT TIME ZONE "
        "USING created_at AT TIME ZONE 'UTC'"
    )
    op.execute(
        "ALTER TABLE events "
        "ALTER COLUMN created_at DROP NOT NULL, "
        "ALTER COLUMN created_at TYPE TIMESTAMP WITHOUT TIME ZONE "
        "USING created_at AT TIME ZONE 'UTC'"
    )
    op.execute(
        "ALTER TABLE agents "
        "ALTER COLUMN created_at DROP NOT NULL, "
        "ALTER COLUMN created_at TYPE TIMESTAMP WITHOUT TIME ZONE "
        "USING created_at AT TIME ZONE 'UTC'"
    )

    op.create_index('idx_events_event_type', 'events', ['event_type'], unique=False)
