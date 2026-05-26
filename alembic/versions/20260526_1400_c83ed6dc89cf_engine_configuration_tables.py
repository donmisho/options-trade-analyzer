"""engine_configuration_tables

Create the five engine_* configuration tables per insight_engine-schema-ddl.md §2:
  - engine_apps (consuming-application registry + SHARED sentinel)
  - engine_rules (atomic rule definitions)
  - engine_strategies (named rule-set + verdict mapping)
  - engine_strategy_rule_junction (per-strategy rule config)
  - engine_lookups (generic keyed config sets)

Structural seed: engine_apps gets SHARED and OTA rows.

Additive only — no ALTER/DROP on any pre-existing table.
bronze_* tables are NOT in scope (later feature).

Revision ID: c83ed6dc89cf
Revises: ade9a09d8001
Create Date: 2026-05-26 14:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c83ed6dc89cf'
down_revision: Union[str, Sequence[str], None] = 'ade9a09d8001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── engine_apps ──────────────────────────────────────────────────────
    op.create_table(
        'engine_apps',
        sa.Column('app_id', sa.String(16), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.String(500), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='active'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('(getutcdate())')),
        sa.PrimaryKeyConstraint('app_id', name='PK_engine_apps'),
        schema='dbo',
    )

    # Structural seed — SHARED sentinel + OTA row
    engine_apps = sa.table(
        'engine_apps',
        sa.column('app_id', sa.String),
        sa.column('name', sa.String),
        sa.column('description', sa.String),
        sa.column('status', sa.String),
    )
    op.bulk_insert(engine_apps, [
        {'app_id': 'SHARED', 'name': 'Shared Rule Library', 'description': 'Cross-app shared rules and lookups', 'status': 'active'},
        {'app_id': 'OTA', 'name': 'Options Trade Analyzer', 'description': 'OTA application', 'status': 'active'},
    ])

    # ── engine_rules ─────────────────────────────────────────────────────
    op.create_table(
        'engine_rules',
        sa.Column('rule_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('owner_app_id', sa.String(16), nullable=False),
        sa.Column('rule_key', sa.String(100), nullable=False),
        sa.Column('phase', sa.String(40), nullable=False),
        sa.Column('tier', sa.String(16), nullable=True),
        sa.Column('intent', sa.String(500), nullable=True),
        sa.Column('condition_expression', sa.String(500), nullable=True),
        sa.Column('formula_ref', sa.String(100), nullable=True),
        sa.Column('referenced_named_values', sa.NVARCHAR(length=None), nullable=True),
        sa.Column('parameter_schema', sa.NVARCHAR(length=None), nullable=True),
        sa.Column('null_semantics', sa.String(20), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('(getutcdate())')),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('rule_id', name='PK_engine_rules'),
        sa.UniqueConstraint('owner_app_id', 'rule_key', name='UQ_engine_rules_owner_key'),
        sa.ForeignKeyConstraint(['owner_app_id'], ['dbo.engine_apps.app_id'], name='FK_engine_rules_app'),
        sa.CheckConstraint(
            'referenced_named_values IS NULL OR ISJSON(referenced_named_values) = 1',
            name='CK_engine_rules_refvals',
        ),
        sa.CheckConstraint(
            'parameter_schema IS NULL OR ISJSON(parameter_schema) = 1',
            name='CK_engine_rules_paramsch',
        ),
        schema='dbo',
    )
    op.create_index(
        'ix_engine_rules_phase',
        'engine_rules',
        ['owner_app_id', 'phase', 'enabled'],
        schema='dbo',
    )

    # ── engine_strategies ────────────────────────────────────────────────
    op.create_table(
        'engine_strategies',
        sa.Column('strategy_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('owner_app_id', sa.String(16), nullable=False),
        sa.Column('strategy_key', sa.String(50), nullable=False),
        sa.Column('display_name', sa.String(100), nullable=False),
        sa.Column('consumer_surface', sa.String(40), nullable=False),
        sa.Column('description', sa.String(None), nullable=True),
        sa.Column('compatible_structures', sa.NVARCHAR(length=None), nullable=True),
        sa.Column('verdict_band_set', sa.NVARCHAR(length=None), nullable=False),
        sa.Column('dte_min', sa.Integer(), nullable=True),
        sa.Column('dte_max', sa.Integer(), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('(getutcdate())')),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('strategy_id', name='PK_engine_strategies'),
        sa.UniqueConstraint('owner_app_id', 'strategy_key', name='UQ_engine_strategies_owner_key'),
        sa.ForeignKeyConstraint(['owner_app_id'], ['dbo.engine_apps.app_id'], name='FK_engine_strategies_app'),
        sa.CheckConstraint(
            'compatible_structures IS NULL OR ISJSON(compatible_structures) = 1',
            name='CK_engine_strategies_struct',
        ),
        sa.CheckConstraint(
            'ISJSON(verdict_band_set) = 1',
            name='CK_engine_strategies_bands',
        ),
        schema='dbo',
    )

    # ── engine_strategy_rule_junction ────────────────────────────────────
    op.create_table(
        'engine_strategy_rule_junction',
        sa.Column('junction_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('strategy_id', sa.Integer(), nullable=False),
        sa.Column('rule_id', sa.Integer(), nullable=False),
        sa.Column('evaluation_order', sa.Integer(), nullable=False),
        sa.Column('stop_if_fail', sa.Boolean(), nullable=False),
        sa.Column('score_penalty', sa.Numeric(6, 2), nullable=True),
        sa.Column('weight', sa.Numeric(7, 4), nullable=True),
        sa.Column('parameters', sa.NVARCHAR(length=None), nullable=True),
        sa.Column('rationale', sa.String(1000), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('(getutcdate())')),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('junction_id', name='PK_engine_junction'),
        sa.UniqueConstraint('strategy_id', 'rule_id', name='UQ_engine_junction'),
        sa.ForeignKeyConstraint(['strategy_id'], ['dbo.engine_strategies.strategy_id'], name='FK_engine_junction_strategy'),
        sa.ForeignKeyConstraint(['rule_id'], ['dbo.engine_rules.rule_id'], name='FK_engine_junction_rule'),
        sa.CheckConstraint(
            'parameters IS NULL OR ISJSON(parameters) = 1',
            name='CK_engine_junction_params',
        ),
        schema='dbo',
    )
    op.create_index(
        'ix_engine_junction_strategy',
        'engine_strategy_rule_junction',
        ['strategy_id', 'enabled'],
        schema='dbo',
    )

    # ── engine_lookups ───────────────────────────────────────────────────
    op.create_table(
        'engine_lookups',
        sa.Column('lookup_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('owner_app_id', sa.String(16), nullable=False),
        sa.Column('lookup_set', sa.String(60), nullable=False),
        sa.Column('lookup_key', sa.String(100), nullable=False),
        sa.Column('payload', sa.NVARCHAR(length=None), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('(getutcdate())')),
        sa.PrimaryKeyConstraint('lookup_id', name='PK_engine_lookups'),
        sa.UniqueConstraint('owner_app_id', 'lookup_set', 'lookup_key', name='UQ_engine_lookups'),
        sa.ForeignKeyConstraint(['owner_app_id'], ['dbo.engine_apps.app_id'], name='FK_engine_lookups_app'),
        sa.CheckConstraint(
            'ISJSON(payload) = 1',
            name='CK_engine_lookups_payload',
        ),
        schema='dbo',
    )


def downgrade() -> None:
    # Reverse dependency order: junction first, then strategies/lookups/rules, then apps
    op.drop_table('engine_strategy_rule_junction', schema='dbo')
    op.drop_table('engine_strategies', schema='dbo')
    op.drop_table('engine_lookups', schema='dbo')
    op.drop_table('engine_rules', schema='dbo')
    op.drop_table('engine_apps', schema='dbo')
