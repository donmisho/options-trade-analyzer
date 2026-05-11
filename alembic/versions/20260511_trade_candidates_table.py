"""Create trade_candidates table (OTA-624)

Persists trade candidate snapshots at scan time so Follow reads from DB
instead of reconstructing from client payload. Enables atomic position
creation and future backtest replay.

Revision ID: a1b2c3d4e5f6
Revises: b8c9d0e1f2a3
Create Date: 2026-05-11 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c7d8e9f01234"
down_revision: Union[str, None] = "b8c9d0e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "trade_candidates",
        sa.Column("trade_key", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("structure", sa.Text(), nullable=False),
        sa.Column("leg_count", sa.Integer(), nullable=False),
        sa.Column("legs", sa.Text(), nullable=True),
        sa.Column("net_metrics", sa.Text(), nullable=True),
        sa.Column("underlying_spot", sa.Numeric(10, 4), nullable=False),
        sa.Column("pipeline_score", sa.Numeric(10, 4), nullable=True),
        sa.Column("pipeline_components", sa.Text(), nullable=True),
        sa.Column("scan_source", sa.Text(), nullable=False),
        sa.Column("scan_strategy_key", sa.Text(), nullable=True),
        sa.Column("scanned_at", sa.DateTime(), nullable=False, server_default=sa.text("GETUTCDATE()")),
        sa.Column("claude_evaluation", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_trade_candidates_user_scanned",
        "trade_candidates",
        ["user_id", "scanned_at"],
    )
    op.create_index(
        "ix_trade_candidates_symbol_user",
        "trade_candidates",
        ["symbol", "user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_trade_candidates_symbol_user", table_name="trade_candidates")
    op.drop_index("ix_trade_candidates_user_scanned", table_name="trade_candidates")
    op.drop_table("trade_candidates")
