"""game foundation: npc + relationship + event_log + policy + save_meta + game_state

Revision ID: f7e8d9a0b1c2
Revises: e5f6a7b8c9da
Create Date: 2026-04-17 00:00:00.000000

Adds the 6 persistence tables for the Tunnels Foundation sub-project
(spec §2 persistence schema). All tables start empty; no data migration.

Singleton invariants:
  * game_state.id = 1 (CHECK)
  * save_meta.id  = 1 (CHECK)
Relationship canonical-order invariant:
  * relationships.npc_a_id < relationships.npc_b_id (CHECK)
  * UNIQUE (npc_a_id, npc_b_id, type) prevents pair duplicates
event_log.tier is restricted to 'P0'/'P1'/'P2'/'P3' (CHECK).

Table create order respects FK dependencies: npcs is created before
relationships (which FK-references npcs). Autogen produced this order
naturally; manually verified.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'f7e8d9a0b1c2'
down_revision = 'e5f6a7b8c9da'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'event_log',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('tick', sa.Integer(), nullable=False),
        sa.Column('tier', sa.String(length=4), nullable=False),
        sa.Column('source_id', sa.Integer(), nullable=True),
        sa.Column('source_type', sa.String(length=16), nullable=True),
        sa.Column(
            'payload_json',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "tier IN ('P0','P1','P2','P3')", name='event_log_tier_valid',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('event_log', schema=None) as batch_op:
        batch_op.create_index(
            'idx_event_log_source', ['source_id', 'source_type'], unique=False,
        )
        batch_op.create_index(
            'idx_event_log_tick_tier', ['tick', 'tier'], unique=False,
        )

    op.create_table(
        'game_state',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tick', sa.Integer(), server_default='0', nullable=False),
        sa.Column('year', sa.Integer(), server_default='0', nullable=False),
        sa.Column(
            'active_layer', sa.String(length=16),
            server_default='life_sim', nullable=False,
        ),
        sa.Column(
            'alignment_axes_json',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.CheckConstraint('id = 1', name='game_state_singleton'),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'npcs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tier', sa.SmallInteger(), nullable=False),
        sa.Column('name', sa.String(length=64), nullable=False),
        sa.Column(
            'stats_json',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            'memory_json',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            'status', sa.String(length=16),
            server_default='alive', nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('npcs', schema=None) as batch_op:
        batch_op.create_index(
            'idx_npcs_tier_status', ['tier', 'status'], unique=False,
        )

    op.create_table(
        'policies',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=32), nullable=False),
        sa.Column(
            'effects_json',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column('active_until_tick', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'save_meta',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column(
            'schema_version', sa.Integer(),
            server_default='1', nullable=False,
        ),
        sa.Column(
            'playtime_seconds', sa.Integer(),
            server_default='0', nullable=False,
        ),
        sa.Column(
            'gen_number', sa.Integer(),
            server_default='1', nullable=False,
        ),
        sa.Column('seed', sa.BigInteger(), nullable=False),
        sa.CheckConstraint('id = 1', name='save_meta_singleton'),
        sa.PrimaryKeyConstraint('id'),
    )

    # npcs must exist before relationships (FK dependency).
    op.create_table(
        'relationships',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('npc_a_id', sa.Integer(), nullable=False),
        sa.Column('npc_b_id', sa.Integer(), nullable=False),
        sa.Column('type', sa.String(length=16), nullable=False),
        sa.Column(
            'strength', sa.SmallInteger(),
            server_default='0', nullable=False,
        ),
        sa.CheckConstraint('npc_a_id < npc_b_id', name='rel_canonical_order'),
        sa.ForeignKeyConstraint(['npc_a_id'], ['npcs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['npc_b_id'], ['npcs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'npc_a_id', 'npc_b_id', 'type',
            name='uq_relationship_pair_type',
        ),
    )
    with op.batch_alter_table('relationships', schema=None) as batch_op:
        batch_op.create_index('idx_rel_a', ['npc_a_id'], unique=False)
        batch_op.create_index('idx_rel_b', ['npc_b_id'], unique=False)

    # Ensure the singleton invariant is enforceable: no row for GameStateRow yet.
    # Seed row is inserted by app.services.game_service.new_game(), not by migration.


def downgrade():
    with op.batch_alter_table('relationships', schema=None) as batch_op:
        batch_op.drop_index('idx_rel_b')
        batch_op.drop_index('idx_rel_a')
    op.drop_table('relationships')

    op.drop_table('save_meta')
    op.drop_table('policies')

    with op.batch_alter_table('npcs', schema=None) as batch_op:
        batch_op.drop_index('idx_npcs_tier_status')
    op.drop_table('npcs')

    op.drop_table('game_state')

    with op.batch_alter_table('event_log', schema=None) as batch_op:
        batch_op.drop_index('idx_event_log_tick_tier')
        batch_op.drop_index('idx_event_log_source')
    op.drop_table('event_log')
