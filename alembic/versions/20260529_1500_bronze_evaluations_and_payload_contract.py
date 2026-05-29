"""bronze_evaluations + bronze_payload_contract tables

Create the two bronze persistence tables per insight_engine-schema-ddl.md §3:
  - bronze_evaluations — single append-only landing table for both engine
    record streams, discriminated by record_type ('SNAPSHOT' | 'DECISION').
    No foreign keys; all references are denormalized soft keys.
  - bronze_payload_contract — self-describing payload registry, unique on
    (record_type, discriminator_value, payload_version).

Additive only — no ALTER/DROP on any pre-existing table.

Revision ID: a1b2c3d4e5f6
Revises: 47c970f0a1f2
Create Date: 2026-05-29 15:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '47c970f0a1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── bronze_evaluations ────────────────────────────────────────────────
    op.create_table(
        'bronze_evaluations',
        # identity / correlation
        sa.Column('record_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('record_type', sa.String(20), nullable=False),
        sa.Column('run_id', sa.String(36), nullable=False),
        sa.Column('snapshot_id', sa.String(36), nullable=False),

        # provenance (stamped on every record)
        sa.Column('source_app_id', sa.String(8), nullable=False),
        sa.Column('config_version', sa.String(64), nullable=False),
        sa.Column('engine_version', sa.String(20), nullable=True),
        sa.Column('evaluated_at', sa.DateTime(), nullable=False),
        sa.Column('payload_version', sa.Integer(), nullable=False),

        # SNAPSHOT-only promoted columns (NULL on DECISION rows)
        sa.Column('candidate_type', sa.String(50), nullable=True),
        sa.Column('strategy_key', sa.String(50), nullable=True),
        sa.Column('symbol', sa.String(20), nullable=True),
        sa.Column('user_id', sa.String(36), nullable=True),
        sa.Column('subject_type', sa.String(40), nullable=True),
        sa.Column('subject_id', sa.String(100), nullable=True),
        sa.Column('final_score', sa.Numeric(6, 2), nullable=True),
        sa.Column('verdict', sa.String(32), nullable=True),
        sa.Column('terminal_phase', sa.String(32), nullable=True),

        # DECISION-only promoted columns (NULL on SNAPSHOT rows)
        sa.Column('rule_key', sa.String(100), nullable=True),
        sa.Column('phase', sa.String(32), nullable=True),
        sa.Column('tier', sa.String(16), nullable=True),
        sa.Column('evaluation_order', sa.Integer(), nullable=True),
        sa.Column('passed', sa.Boolean(), nullable=True),
        sa.Column('stop_if_fail', sa.Boolean(), nullable=True),
        sa.Column('was_terminal', sa.Boolean(), nullable=True),
        sa.Column('score_contribution', sa.Numeric(8, 2), nullable=True),

        # payload
        sa.Column('payload_json', sa.NVARCHAR(length=None), nullable=True),

        # constraints
        sa.PrimaryKeyConstraint('record_id', name='PK_bronze_evaluations'),
        sa.CheckConstraint(
            "payload_json IS NULL OR ISJSON(payload_json) = 1",
            name='CK_bronze_evaluations_payload',
        ),
        sa.CheckConstraint(
            "record_type IN ('SNAPSHOT','DECISION')",
            name='CK_bronze_evaluations_type',
        ),
        schema='dbo',
    )

    # Indexes per §3
    op.create_index(
        'ix_bronze_run', 'bronze_evaluations', ['run_id'], schema='dbo',
    )
    op.create_index(
        'ix_bronze_snapshot', 'bronze_evaluations', ['snapshot_id'], schema='dbo',
    )
    op.create_index(
        'ix_bronze_app_type_time', 'bronze_evaluations',
        ['source_app_id', 'record_type', sa.text('evaluated_at DESC')],
        schema='dbo',
    )
    # Filtered indexes (WHERE ... IS NOT NULL)
    op.execute(
        'CREATE INDEX ix_bronze_user_time ON dbo.bronze_evaluations '
        '(user_id, evaluated_at DESC) WHERE user_id IS NOT NULL'
    )
    op.execute(
        'CREATE INDEX ix_bronze_subject ON dbo.bronze_evaluations '
        '(subject_type, subject_id) WHERE subject_id IS NOT NULL'
    )
    op.execute(
        'CREATE INDEX ix_bronze_symbol_time ON dbo.bronze_evaluations '
        '(symbol, evaluated_at DESC) WHERE symbol IS NOT NULL'
    )
    op.execute(
        'CREATE INDEX ix_bronze_rule ON dbo.bronze_evaluations '
        '(rule_key) WHERE rule_key IS NOT NULL'
    )

    # ── bronze_payload_contract ───────────────────────────────────────────
    op.create_table(
        'bronze_payload_contract',
        sa.Column('contract_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('record_type', sa.String(20), nullable=False),
        sa.Column('discriminator_value', sa.String(50), nullable=False),
        sa.Column('payload_version', sa.Integer(), nullable=False),
        sa.Column('shape_description', sa.NVARCHAR(length=None), nullable=True),
        sa.Column('source_app_id', sa.String(8), nullable=True),
        sa.Column('registered_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('(getutcdate())')),
        sa.PrimaryKeyConstraint('contract_id', name='PK_bronze_payload_contract'),
        sa.UniqueConstraint('record_type', 'discriminator_value', 'payload_version',
                            name='UQ_bronze_payload_contract'),
        schema='dbo',
    )


def downgrade() -> None:
    op.drop_table('bronze_payload_contract', schema='dbo')
    op.drop_table('bronze_evaluations', schema='dbo')
