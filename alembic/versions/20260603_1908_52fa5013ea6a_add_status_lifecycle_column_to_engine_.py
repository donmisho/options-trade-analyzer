"""add status lifecycle column to engine_strategies

Add a `status` lifecycle column to dbo.engine_strategies per
insight_engine-schema-ddl.md §2 (OTA-822). Additive only.

Domain (active | inactive | deprecated | draft) is enforced at the
write/model layer (OTA-824), NOT via a DB CHECK constraint — mirrors the
OTA-709 "validate at load, not via DB constraint" precedent.

status <-> enabled invariant (defined here, enforced on writes by OTA-824):
  status='active'                         <=> enabled=1
  status IN ('inactive','deprecated','draft') => enabled=0

Backfill: enabled=1 -> 'active' (the column default), enabled=0 -> 'inactive'.

Runtime loader is UNCHANGED — AzureSqlConfigSource still SELECTs all rows and
the engine loader filters enabled=1, so non-active/draft rows stay excluded
from the live engine (OTA-818 keystone untouched).

Revision ID: 52fa5013ea6a
Revises: ff832488933d
Create Date: 2026-06-03 19:08:41.704724

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '52fa5013ea6a'
down_revision: Union[str, Sequence[str], None] = 'ff832488933d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add status column (default 'active') and backfill from enabled."""
    op.add_column(
        'engine_strategies',
        sa.Column(
            'status',
            sa.String(16),
            nullable=False,
            server_default='active',
        ),
        schema='dbo',
    )
    # Backfill: rows already default to 'active' (enabled=1); flip disabled
    # rows to 'inactive' to honour the status<->enabled invariant.
    op.execute(
        "UPDATE dbo.engine_strategies SET status = 'inactive' WHERE enabled = 0"
    )


def downgrade() -> None:
    """Drop the status column (and its DEFAULT constraint on SQL Server)."""
    op.drop_column(
        'engine_strategies',
        'status',
        schema='dbo',
        mssql_drop_default=True,
    )
