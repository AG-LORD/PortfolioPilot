"""create ml_forecasts; add recommendation_snapshots.forecast_source

Revision ID: e7a1c4b92d30
Revises: d93f4cb182ea
Create Date: 2026-09-26 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e7a1c4b92d30"
down_revision: Union[str, Sequence[str], None] = "d93f4cb182ea"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ml_forecasts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ticker", sa.String(length=20), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("horizon", sa.Integer(), nullable=False),
        sa.Column("model_version", sa.String(length=100), nullable=False),
        sa.Column("raw_forecast", sa.Numeric(), nullable=False),
        sa.Column("annual_forecast", sa.Numeric(), nullable=False),
        sa.Column("clipped", sa.Boolean(), nullable=False),
        sa.Column("drivers", sa.JSON(), nullable=False),
        sa.Column("typical_estimate", sa.Numeric(), nullable=True),
        sa.Column("training_start", sa.Date(), nullable=False),
        sa.Column("training_end", sa.Date(), nullable=False),
        sa.Column("training_rows", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticker", "as_of", "horizon", "model_version", name="uq_ml_forecast_ticker_asof_horizon_version"),
    )
    op.add_column(
        "recommendation_snapshots",
        sa.Column("forecast_source", sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("recommendation_snapshots", "forecast_source")
    op.drop_table("ml_forecasts")
