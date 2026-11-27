"""Entry signals table (signal monitor)

One additive table, entry_signals: the current entry-signal state of each watched
underlying, rewritten every minute in market hours by the signal monitor and read
by the get_signals MCP tool. One row per user and symbol; no history is kept.

Expand-only (deployment-workflow.md § Database migration discipline): no ALTER or
DROP on any existing table. Carries user_id (Data Isolation Invariant). Types are
portable so the same migration runs on Azure SQL and on the SQLite dev database.

Revision ID: c4d8e2f6a9b3
Revises: b7c2d4e6f8a1
Create Date: 2026-11-27 15:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c4d8e2f6a9b3"
down_revision: Union[str, Sequence[str], None] = "b7c2d4e6f8a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "entry_signals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("direction", sa.String(4), nullable=True),
        sa.Column("message", sa.String(400), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(), nullable=False),
        sa.Column("status_since", sa.DateTime(), nullable=False),
        sa.Column("last_bar_at", sa.DateTime(), nullable=True),
        sa.Column("push_bar_at", sa.DateTime(), nullable=True),
        sa.Column("price", sa.Float(), nullable=True),
        sa.Column("vwap", sa.Float(), nullable=True),
        sa.Column("trend_15m", sa.String(5), nullable=True),
        sa.Column("push", sa.Float(), nullable=True),
        sa.Column("push_pct_atr", sa.Float(), nullable=True),
        sa.Column("push_strong", sa.Boolean(), nullable=True),
        sa.Column("volume_ratio", sa.Float(), nullable=True),
        sa.Column("atr", sa.Float(), nullable=True),
        sa.Column("prev_close", sa.Float(), nullable=True),
        sa.Column("net_change", sa.Float(), nullable=True),
        sa.Column("atr_used_pct", sa.Float(), nullable=True),
        sa.Column("range_used_pct", sa.Float(), nullable=True),
        sa.Column("gate_trend", sa.Boolean(), nullable=True),
        sa.Column("gate_push", sa.Boolean(), nullable=True),
        sa.Column("gate_volume", sa.Boolean(), nullable=True),
        sa.Column("gate_room", sa.Boolean(), nullable=True),
        sa.Column("gate_contract", sa.Boolean(), nullable=True),
        sa.Column("option_symbol", sa.String(30), nullable=True),
        sa.Column("put_call", sa.String(4), nullable=True),
        sa.Column("expiration", sa.String(10), nullable=True),
        sa.Column("dte", sa.Integer(), nullable=True),
        sa.Column("strike", sa.Float(), nullable=True),
        sa.Column("delta", sa.Float(), nullable=True),
        sa.Column("option_bid", sa.Float(), nullable=True),
        sa.Column("option_ask", sa.Float(), nullable=True),
        sa.Column("option_mid", sa.Float(), nullable=True),
        sa.Column("spread_pct", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "symbol", name="uq_entry_signals_user_symbol"),
    )


def downgrade() -> None:
    op.drop_table("entry_signals")
