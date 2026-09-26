"""allow explicit capital deposit transactions

Revision ID: a4d5f9c3b8e1
Revises: 7c3d9a1f5e42
Create Date: 2026-09-26 10:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a4d5f9c3b8e1"
down_revision: Union[str, Sequence[str], None] = "7c3d9a1f5e42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("ck_transaction_type", "transactions", type_="check")
    op.create_check_constraint(
        "ck_transaction_type",
        "transactions",
        "transaction_type IN ('BUY', 'SELL', 'DEPOSIT')",
    )


def downgrade() -> None:
    has_deposits = op.get_bind().execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM transactions WHERE transaction_type = 'DEPOSIT')")
    ).scalar_one()
    if has_deposits:
        raise RuntimeError("Cannot remove DEPOSIT while capital transactions are persisted")

    op.drop_constraint("ck_transaction_type", "transactions", type_="check")
    op.create_check_constraint(
        "ck_transaction_type",
        "transactions",
        "transaction_type IN ('BUY', 'SELL')",
    )