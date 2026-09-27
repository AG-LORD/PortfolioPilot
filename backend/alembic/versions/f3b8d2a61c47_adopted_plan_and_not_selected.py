"""add portfolios.adopted_recommendation_id/adopted_at and recommendation_snapshots.not_selected

Revision ID: f3b8d2a61c47
Revises: e7a1c4b92d30
Create Date: 2026-09-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f3b8d2a61c47"
down_revision: Union[str, Sequence[str], None] = "e7a1c4b92d30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("portfolios", sa.Column("adopted_recommendation_id", sa.Uuid(), nullable=True))
    op.add_column("portfolios", sa.Column("adopted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        "fk_portfolios_adopted_recommendation_id",
        "portfolios",
        "recommendation_snapshots",
        ["adopted_recommendation_id"],
        ["id"],
        ondelete="SET NULL",
    )
    # Null for snapshots saved before this column existed; the API reads null as [].
    op.add_column("recommendation_snapshots", sa.Column("not_selected", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("recommendation_snapshots", "not_selected")
    op.drop_constraint("fk_portfolios_adopted_recommendation_id", "portfolios", type_="foreignkey")
    op.drop_column("portfolios", "adopted_at")
    op.drop_column("portfolios", "adopted_recommendation_id")
