"""create persisted rebalance proposals

Revision ID: d93f4cb182ea
Revises: c6f2a913d74b
Create Date: 2026-09-26 11:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d93f4cb182ea"
down_revision: Union[str, Sequence[str], None] = "c6f2a913d74b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rebalance_proposals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("portfolio_id", sa.Uuid(), nullable=False),
        sa.Column("recommendation_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="PENDING", nullable=False),
        sa.Column("state_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("portfolio_value", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("cash_before", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("projected_cash", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("buy_total", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("sell_total", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("estimated_fees", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("fee_assumption", sa.String(length=255), nullable=False),
        sa.Column("trades", sa.JSON(), nullable=False),
        sa.Column("resulting_weights", sa.JSON(), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('PENDING', 'EXECUTED', 'EXPIRED')", name="ck_rebalance_proposal_status"),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.id"]),
        sa.ForeignKeyConstraint(["recommendation_id"], ["recommendation_snapshots.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_rebalance_proposals_portfolio_created_at",
        "rebalance_proposals",
        ["portfolio_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_rebalance_proposals_portfolio_created_at", table_name="rebalance_proposals")
    op.drop_table("rebalance_proposals")