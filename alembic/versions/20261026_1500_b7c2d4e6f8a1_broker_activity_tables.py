"""Broker account activity tables (OTA-855)

Five additive tables for the Schwab account activity poller:
  - broker_accounts      the accounts the poller reads (hash, last4, label)
  - broker_transactions  one row per Trader API transaction, raw JSON kept
  - broker_orders        one row per order / child order, upserted as state changes
  - broker_fill_context  the market read around each option fill (ATR used, spread)
  - broker_sync_runs     one row per poller run

Expand-only (deployment-workflow.md § Database migration discipline): no ALTER
or DROP on any existing table. Every table carries user_id (Data Isolation
Invariant). Types are portable so the same migration runs on Azure SQL and on
the SQLite dev database.

Revision ID: b7c2d4e6f8a1
Revises: a3f1c9e07b42
Create Date: 2026-10-26 15:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7c2d4e6f8a1"
down_revision: Union[str, Sequence[str], None] = "a3f1c9e07b42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "broker_accounts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False, server_default="schwab"),
        sa.Column("account_hash", sa.String(64), nullable=False),
        sa.Column("account_last4", sa.String(4), nullable=False),
        sa.Column("label", sa.String(40), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("last_synced_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "provider", "account_hash", name="uq_broker_accounts_user_hash"),
    )

    op.create_table(
        "broker_transactions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("broker_accounts.id"), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False, server_default="schwab"),
        sa.Column("activity_id", sa.BigInteger(), nullable=False),
        sa.Column("order_id", sa.BigInteger(), nullable=True),
        sa.Column("position_id", sa.BigInteger(), nullable=True),
        sa.Column("activity_type", sa.String(30), nullable=True),
        sa.Column("transaction_type", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=True),
        sa.Column("sub_account", sa.String(20), nullable=True),
        sa.Column("time", sa.DateTime(), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("settlement_date", sa.Date(), nullable=True),
        sa.Column("description", sa.String(400), nullable=True),
        sa.Column("asset_type", sa.String(20), nullable=True),
        sa.Column("structure", sa.String(20), nullable=True),
        sa.Column("side", sa.String(4), nullable=True),
        sa.Column("position_effect", sa.String(10), nullable=True),
        sa.Column("underlying_symbol", sa.String(20), nullable=True),
        sa.Column("option_symbol", sa.String(30), nullable=True),
        sa.Column("put_call", sa.String(4), nullable=True),
        sa.Column("strike_price", sa.Numeric(12, 4), nullable=True),
        sa.Column("strikes_text", sa.String(60), nullable=True),
        sa.Column("expiration_date", sa.Date(), nullable=True),
        sa.Column("quantity", sa.Numeric(12, 4), nullable=True),
        sa.Column("price", sa.Numeric(14, 4), nullable=True),
        sa.Column("leg_cost", sa.Numeric(14, 4), nullable=True),
        sa.Column("commissions", sa.Numeric(14, 4), nullable=True),
        sa.Column("fees", sa.Numeric(14, 4), nullable=True),
        sa.Column("net_amount", sa.Numeric(14, 4), nullable=True),
        sa.Column("leg_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("legs_json", sa.Text(), nullable=True),
        sa.Column("raw_json", sa.Text(), nullable=False),
        sa.Column("captured_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "activity_id", name="uq_broker_transactions_activity"),
    )
    op.create_index("ix_broker_transactions_user_time", "broker_transactions", ["user_id", "time"])
    op.create_index("ix_broker_transactions_order", "broker_transactions", ["order_id"])

    op.create_table(
        "broker_orders",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("broker_accounts.id"), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False, server_default="schwab"),
        sa.Column("order_id", sa.BigInteger(), nullable=False),
        sa.Column("parent_order_id", sa.BigInteger(), nullable=True),
        sa.Column("order_strategy_type", sa.String(20), nullable=True),
        sa.Column("order_type", sa.String(20), nullable=True),
        sa.Column("status", sa.String(30), nullable=True),
        sa.Column("status_description", sa.String(400), nullable=True),
        sa.Column("session", sa.String(20), nullable=True),
        sa.Column("duration", sa.String(30), nullable=True),
        sa.Column("price", sa.Numeric(14, 4), nullable=True),
        sa.Column("stop_price", sa.Numeric(14, 4), nullable=True),
        sa.Column("stop_price_link_basis", sa.String(20), nullable=True),
        sa.Column("stop_price_link_type", sa.String(20), nullable=True),
        sa.Column("stop_price_offset", sa.Numeric(14, 4), nullable=True),
        sa.Column("stop_type", sa.String(20), nullable=True),
        sa.Column("entered_time", sa.DateTime(), nullable=True),
        sa.Column("close_time", sa.DateTime(), nullable=True),
        sa.Column("quantity", sa.Numeric(12, 4), nullable=True),
        sa.Column("filled_quantity", sa.Numeric(12, 4), nullable=True),
        sa.Column("remaining_quantity", sa.Numeric(12, 4), nullable=True),
        sa.Column("instruction", sa.String(20), nullable=True),
        sa.Column("position_effect", sa.String(10), nullable=True),
        sa.Column("structure", sa.String(20), nullable=True),
        sa.Column("underlying_symbol", sa.String(20), nullable=True),
        sa.Column("option_symbol", sa.String(30), nullable=True),
        sa.Column("put_call", sa.String(4), nullable=True),
        sa.Column("strike_price", sa.Numeric(12, 4), nullable=True),
        sa.Column("strikes_text", sa.String(60), nullable=True),
        sa.Column("expiration_date", sa.Date(), nullable=True),
        sa.Column("leg_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("legs_json", sa.Text(), nullable=True),
        sa.Column("raw_json", sa.Text(), nullable=False),
        sa.Column("captured_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "order_id", name="uq_broker_orders_order"),
    )
    op.create_index("ix_broker_orders_user_entered", "broker_orders", ["user_id", "entered_time"])
    op.create_index("ix_broker_orders_parent", "broker_orders", ["parent_order_id"])

    op.create_table(
        "broker_fill_context",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("transaction_id", sa.Integer(), sa.ForeignKey("broker_transactions.id"), nullable=False),
        sa.Column("captured_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("kind", sa.String(12), nullable=False, server_default="live"),
        sa.Column("lag_seconds", sa.Integer(), nullable=True),
        sa.Column("underlying_symbol", sa.String(20), nullable=True),
        sa.Column("underlying_last", sa.Numeric(14, 4), nullable=True),
        sa.Column("underlying_net_change", sa.Numeric(14, 4), nullable=True),
        sa.Column("underlying_prev_close", sa.Numeric(14, 4), nullable=True),
        sa.Column("atr14", sa.Numeric(14, 4), nullable=True),
        sa.Column("atr_as_of", sa.Date(), nullable=True),
        sa.Column("atr_used", sa.Float(), nullable=True),
        sa.Column("option_symbol", sa.String(30), nullable=True),
        sa.Column("option_bid", sa.Numeric(14, 4), nullable=True),
        sa.Column("option_ask", sa.Numeric(14, 4), nullable=True),
        sa.Column("option_mark", sa.Numeric(14, 4), nullable=True),
        sa.Column("option_last", sa.Numeric(14, 4), nullable=True),
        sa.Column("spread", sa.Numeric(14, 4), nullable=True),
        sa.Column("spread_pct_mid", sa.Float(), nullable=True),
        sa.Column("open_interest", sa.Integer(), nullable=True),
        sa.Column("option_volume", sa.Integer(), nullable=True),
        sa.Column("raw_json", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("transaction_id", name="uq_broker_fill_context_transaction"),
    )
    op.create_index("ix_broker_fill_context_user", "broker_fill_context", ["user_id"])

    op.create_table(
        "broker_sync_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("trigger", sa.String(20), nullable=False, server_default="schedule"),
        sa.Column("window_start", sa.DateTime(), nullable=True),
        sa.Column("window_end", sa.DateTime(), nullable=True),
        sa.Column("accounts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("transactions_new", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("orders_upserted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("contexts_captured", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("message", sa.String(1000), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_broker_sync_runs_started", "broker_sync_runs", ["started_at"])


def downgrade() -> None:
    op.drop_index("ix_broker_sync_runs_started", table_name="broker_sync_runs")
    op.drop_table("broker_sync_runs")
    op.drop_index("ix_broker_fill_context_user", table_name="broker_fill_context")
    op.drop_table("broker_fill_context")
    op.drop_index("ix_broker_orders_parent", table_name="broker_orders")
    op.drop_index("ix_broker_orders_user_entered", table_name="broker_orders")
    op.drop_table("broker_orders")
    op.drop_index("ix_broker_transactions_order", table_name="broker_transactions")
    op.drop_index("ix_broker_transactions_user_time", table_name="broker_transactions")
    op.drop_table("broker_transactions")
    op.drop_table("broker_accounts")
