"""Add deploy_log table (OTA-602)

Revision ID: a1b2c3d4e5f6
Revises: f9e59a180957
Create Date: 2026-05-06 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "f9e59a180957"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "deploy_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("build_id", sa.String(64), nullable=False),
        sa.Column("environment", sa.String(16), nullable=False),
        sa.Column("deployed_at", sa.DateTime(), nullable=False),
        sa.Column("commit_sha", sa.String(40), nullable=False),
        sa.Column("ticket_keys", sa.String(500), nullable=False),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_deploy_log_deployed_at", "deploy_log", ["deployed_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_deploy_log_deployed_at", table_name="deploy_log")
    op.drop_table("deploy_log")
