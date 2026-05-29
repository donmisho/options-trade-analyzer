"""add terminal_verdict to engine_strategy_rule_junction

Revision ID: 47c970f0a1f2
Revises: c83ed6dc89cf
Create Date: 2026-05-28 21:26:46.130319

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '47c970f0a1f2'
down_revision: Union[str, Sequence[str], None] = 'c83ed6dc89cf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'engine_strategy_rule_junction',
        sa.Column('terminal_verdict', sa.String(32), nullable=True),
        schema='dbo',
    )


def downgrade() -> None:
    op.drop_column(
        'engine_strategy_rule_junction',
        'terminal_verdict',
        schema='dbo',
    )
