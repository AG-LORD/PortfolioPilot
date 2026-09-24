"""add daily price cache (daily_prices, price_cache_coverage)

Revision ID: 7c3d9a1f5e42
Revises: 2b8e4f5015de
Create Date: 2026-09-24 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7c3d9a1f5e42'
down_revision: Union[str, Sequence[str], None] = '2b8e4f5015de'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'daily_prices',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('ticker', sa.String(length=20), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('open', sa.Numeric(), nullable=False),
        sa.Column('high', sa.Numeric(), nullable=False),
        sa.Column('low', sa.Numeric(), nullable=False),
        sa.Column('close', sa.Numeric(), nullable=False),
        sa.Column('volume', sa.BigInteger(), nullable=False),
        sa.Column('source', sa.String(length=30), nullable=False),
        sa.Column(
            'fetched_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ticker', 'date', name='uq_daily_price_ticker_date'),
    )
    op.create_table(
        'price_cache_coverage',
        sa.Column('ticker', sa.String(length=20), nullable=False),
        sa.Column('covered_start', sa.Date(), nullable=False),
        sa.Column('covered_end', sa.Date(), nullable=False),
        sa.Column('last_full_refresh_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            'covered_start <= covered_end', name='ck_price_cache_coverage_range'
        ),
        sa.PrimaryKeyConstraint('ticker'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('price_cache_coverage')
    op.drop_table('daily_prices')
