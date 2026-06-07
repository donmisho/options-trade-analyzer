"""engine_config_audit table (OTA-792)

Create the append-only config-change audit trail per OTA-792:
  - engine_config_audit — one row per config change committed through the
    OTA-782 CRUD path (strategy / rule / junction / lookup) plus one row per
    OTA-790 Apply promotion. Records actor (BFF identity), UTC timestamp, the
    target row's soft keys, a before/after image of the changed fields, the
    loadable-set version stamp the change produces, and a draft-vs-live flag.

Bronze convention (insight_engine-schema-ddl.md §1): append-only, NO foreign
keys into the config tables — every reference out is a denormalized soft key
(strategy_key / rule_key / lookup_set+lookup_key), so the trail outlives the
rows it describes. Isolation is by owning app (source_app_id), not actor —
user_id is recorded for accountability only.

Additive only (expand migration) — no ALTER/DROP on any pre-existing table.

Revision ID: a3f1c9e07b42
Revises: 52fa5013ea6a
Create Date: 2026-06-07 15:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3f1c9e07b42'
down_revision: Union[str, Sequence[str], None] = '52fa5013ea6a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'engine_config_audit',
        sa.Column('audit_id', sa.BigInteger(), autoincrement=True, nullable=False),
        # provenance / actor
        sa.Column('source_app_id', sa.String(8), nullable=False,
                  server_default='OTA'),
        sa.Column('user_id', sa.String(36), nullable=False),
        sa.Column('actor_label', sa.String(200), nullable=True),
        sa.Column('occurred_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('(getutcdate())')),
        # target discriminator + operation + draft-vs-live stage
        sa.Column('entity_type', sa.String(40), nullable=False),
        sa.Column('operation', sa.String(20), nullable=False),
        sa.Column('target_stage', sa.String(8), nullable=False),
        # denormalized soft keys (no FKs into config tables)
        sa.Column('strategy_key', sa.String(50), nullable=True),
        sa.Column('rule_key', sa.String(100), nullable=True),
        sa.Column('lookup_set', sa.String(60), nullable=True),
        sa.Column('lookup_key', sa.String(100), nullable=True),
        # before/after row images of the changed fields
        sa.Column('before_json', sa.NVARCHAR(length=None), nullable=True),
        sa.Column('after_json', sa.NVARCHAR(length=None), nullable=True),
        # the loadable-set hash the change produces (OTA-790 version stamp)
        sa.Column('loadable_version', sa.String(64), nullable=True),
        # constraints
        sa.PrimaryKeyConstraint('audit_id', name='PK_engine_config_audit'),
        sa.CheckConstraint(
            "before_json IS NULL OR ISJSON(before_json) = 1",
            name='CK_engine_config_audit_before',
        ),
        sa.CheckConstraint(
            "after_json IS NULL OR ISJSON(after_json) = 1",
            name='CK_engine_config_audit_after',
        ),
        schema='dbo',
    )

    # Full-trail ordering + accountability lookups.
    op.create_index(
        'ix_config_audit_time', 'engine_config_audit',
        [sa.text('occurred_at DESC')], schema='dbo',
    )
    op.create_index(
        'ix_config_audit_user_time', 'engine_config_audit',
        ['user_id', sa.text('occurred_at DESC')], schema='dbo',
    )
    # Per-entity trail filters (filtered indexes — only rows that carry the key).
    op.execute(
        'CREATE INDEX ix_config_audit_strategy_time ON dbo.engine_config_audit '
        '(strategy_key, occurred_at DESC) WHERE strategy_key IS NOT NULL'
    )
    op.execute(
        'CREATE INDEX ix_config_audit_rule_time ON dbo.engine_config_audit '
        '(rule_key, occurred_at DESC) WHERE rule_key IS NOT NULL'
    )


def downgrade() -> None:
    op.drop_table('engine_config_audit', schema='dbo')
