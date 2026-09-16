from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from decimal import Decimal
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    func,
)

from app.database import Base

class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

class RiskProfile(Base):
    __tablename__ = "risk_profiles"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("user_profiles.id"),
        nullable=False,
    )

    score: Mapped[Decimal] = mapped_column(
        Numeric(8, 4),
        nullable=False,
    )
    category: Mapped[str] = mapped_column(String(50), nullable=False)

    max_position_weight: Mapped[Decimal] = mapped_column(
        Numeric(8, 6),
        nullable=False,
    )
    max_sector_weight: Mapped[Decimal] = mapped_column(
        Numeric(8, 6),
        nullable=False,
    )
    drift_threshold: Mapped[Decimal] = mapped_column(
        Numeric(8, 6),
        nullable=False,
    )
    target_volatility: Mapped[Decimal] = mapped_column(
        Numeric(8, 6),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

class Portfolio(Base):
    __tablename__ = "portfolios"

    __table_args__ = (
        CheckConstraint(
            "initial_capital >= 0",
            name="ck_portfolio_initial_capital_nonnegative",
        ),
        CheckConstraint(
            "cash_balance >= 0",
            name="ck_portfolio_cash_nonnegative",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("user_profiles.id"),
        nullable=False,
    )

    risk_profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("risk_profiles.id"),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    purpose: Mapped[str | None] = mapped_column(String(255), nullable=True)
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    initial_capital: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
    )

    cash_balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

class Holding(Base):
    __tablename__ = "holdings"

    __table_args__ = (
        UniqueConstraint(
            "portfolio_id",
            "ticker",
            name="uq_holding_portfolio_ticker",
        ),
        CheckConstraint(
            "quantity > 0",
            name="ck_holding_quantity_positive",
        ),
        CheckConstraint(
            "average_cost >= 0",
            name="ck_holding_average_cost_nonnegative",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

    portfolio_id: Mapped[UUID] = mapped_column(nullable=False)

    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(20, 6),
        nullable=False,
    )

    average_cost: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )



class Transaction(Base):
    __tablename__ = "transactions"

    __table_args__ = (
        CheckConstraint(
            "quantity > 0",
            name="ck_transaction_quantity_positive",
        ),
        CheckConstraint(
            "price >= 0",
            name="ck_transaction_price_nonnegative",
        ),
        CheckConstraint(
            "fees >= 0",
            name="ck_transaction_fees_nonnegative",
        ),
        CheckConstraint(
            "transaction_type IN ('BUY', 'SELL')",
            name="ck_transaction_type",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

    portfolio_id: Mapped[UUID] = mapped_column(
        ForeignKey("portfolios.id"),
        nullable=False,
    )

    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(10), nullable=False)

    quantity: Mapped[Decimal] = mapped_column(
        Numeric(20, 6),
        nullable=False,
    )

    price: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
    )

    fees: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
    )

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    source: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

    portfolio_id: Mapped[UUID] = mapped_column(
        ForeignKey("portfolios.id"),
        nullable=False,
    )

    snapshot_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    total_value: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
    )

    cash_balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
    )

    invested_value: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
    )

    daily_return: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 8),
        nullable=True,
    )

    cumulative_return: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 8),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )