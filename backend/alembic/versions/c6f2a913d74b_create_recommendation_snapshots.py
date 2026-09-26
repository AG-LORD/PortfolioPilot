"""create immutable recommendation snapshots

Revision ID: c6f2a913d74b
Revises: a4d5f9c3b8e1
Create Date: 2026-09-26 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c6f2a913d74b"
down_revision: Union[str, Sequence[str], None] = "a4d5f9c3b8e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "recommendation_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("portfolio_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("capital", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("universe", sa.String(length=100), nullable=False),
        sa.Column("universe_as_of", sa.Date(), nullable=True),
        sa.Column("return_model", sa.String(length=20), nullable=False),
        sa.Column("model_version", sa.String(length=100), nullable=True),
        sa.Column("forecast_as_of", sa.Date(), nullable=True),
        sa.Column("expected_portfolio_return", sa.Numeric(precision=12, scale=8), nullable=False),
        sa.Column("expected_portfolio_volatility", sa.Numeric(precision=12, scale=8), nullable=False),
        sa.Column("cash_weight", sa.Numeric(precision=12, scale=8), nullable=False),
        sa.Column("cash_amount", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("max_position_weight", sa.Numeric(precision=8, scale=6), nullable=False),
        sa.Column("target_volatility", sa.Numeric(precision=8, scale=6), nullable=False),
        sa.Column("allocations", sa.JSON(), nullable=False),
        sa.Column("excluded", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_recommendation_snapshots_portfolio_created_at",
        "recommendation_snapshots",
        ["portfolio_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_recommendation_snapshots_portfolio_created_at",
        table_name="recommendation_snapshots",
    )
    op.drop_table("recommendation_snapshots")