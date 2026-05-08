"""Fix symbol_reference ETF data for OTA-608

Insert missing ETFs (SPY, IWM, DIA) and fix QQQ misclassification
from Equity to ETF. These rows are required by the get_earnings_date
MCP tool's ETF detection logic.

Revision ID: b8c9d0e1f2a3
Revises: 6dafa62d4553
Create Date: 2026-05-08 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, None] = "6dafa62d4553"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Fix QQQ: misclassified as Equity, should be ETF
    op.execute(
        sa.text(
            "UPDATE symbol_reference SET asset_type = 'ETF' WHERE symbol = 'QQQ'"
        )
    )

    # Insert missing ETFs from the OTA-608 acceptance matrix
    op.execute(
        sa.text(
            "INSERT INTO symbol_reference (symbol, name, exchange, sector, sub_industry, asset_type, last_updated) "
            "VALUES ('SPY', 'SPDR S&P 500 ETF Trust', 'NYSE Arca', '', '', 'ETF', GETUTCDATE())"
        )
    )
    op.execute(
        sa.text(
            "INSERT INTO symbol_reference (symbol, name, exchange, sector, sub_industry, asset_type, last_updated) "
            "VALUES ('IWM', 'iShares Russell 2000 ETF', 'NYSE Arca', '', '', 'ETF', GETUTCDATE())"
        )
    )
    op.execute(
        sa.text(
            "INSERT INTO symbol_reference (symbol, name, exchange, sector, sub_industry, asset_type, last_updated) "
            "VALUES ('DIA', 'SPDR Dow Jones Industrial Average ETF Trust', 'NYSE Arca', '', '', 'ETF', GETUTCDATE())"
        )
    )


def downgrade() -> None:
    # Revert QQQ back to Equity
    op.execute(
        sa.text(
            "UPDATE symbol_reference SET asset_type = 'Equity' WHERE symbol = 'QQQ'"
        )
    )
    # Remove the three inserted ETFs
    op.execute(
        sa.text(
            "DELETE FROM symbol_reference WHERE symbol IN ('SPY', 'IWM', 'DIA')"
        )
    )
