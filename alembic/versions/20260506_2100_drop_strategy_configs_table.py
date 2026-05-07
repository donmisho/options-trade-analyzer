"""Drop strategy_configs table (OTA-546 Option B)

Strategy config persistence is handled by frontend localStorage.
The strategy_configs table was created but never populated or wired to API routes.

Revision ID: 6dafa62d4553
Revises: a1b2c3d4e5f6
Create Date: 2026-05-06 21:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "6dafa62d4553"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_strategy_configs_user_key", table_name="strategy_configs")
    op.drop_table("strategy_configs")


def downgrade() -> None:
    op.create_table(
        "strategy_configs",
        sa.Column("config_id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("strategy_key", sa.String(50), nullable=False),
        sa.Column("config_json", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime),
        sa.Column("updated_at", sa.DateTime),
    )
    op.create_index(
        "ix_strategy_configs_user_key",
        "strategy_configs",
        ["user_id", "strategy_key"],
    )
