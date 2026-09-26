from datetime import date as calendar_date
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from decimal import Decimal
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
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
    portfolio_id: Mapped[UUID] = mapped_column(
    ForeignKey("portfolios.id"),
    nullable=False,
)


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
            "transaction_type IN ('BUY', 'SELL', 'DEPOSIT')",
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

class RecommendationSnapshot(Base):
    __tablename__ = "recommendation_snapshots"
    __table_args__ = (
        Index(
            "ix_recommendation_snapshots_portfolio_created_at",
            "portfolio_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    portfolio_id: Mapped[UUID] = mapped_column(
        ForeignKey("portfolios.id"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    capital: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    universe: Mapped[str] = mapped_column(String(100), nullable=False)
    universe_as_of: Mapped[calendar_date | None] = mapped_column(Date, nullable=True)
    return_model: Mapped[str] = mapped_column(String(20), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    forecast_as_of: Mapped[calendar_date | None] = mapped_column(Date, nullable=True)
    # "precomputed" (nightly run), "on_request", or null when no ML forecast was used.
    forecast_source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    expected_portfolio_return: Mapped[Decimal] = mapped_column(Numeric(12, 8), nullable=False)
    expected_portfolio_volatility: Mapped[Decimal] = mapped_column(Numeric(12, 8), nullable=False)
    cash_weight: Mapped[Decimal] = mapped_column(Numeric(12, 8), nullable=False)
    cash_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    max_position_weight: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False)
    target_volatility: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False)
    allocations: Mapped[dict] = mapped_column(JSON, nullable=False)
    excluded: Mapped[dict] = mapped_column(JSON, nullable=False)


class RebalanceProposal(Base):
    __tablename__ = "rebalance_proposals"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'EXECUTED', 'EXPIRED')",
            name="ck_rebalance_proposal_status",
        ),
        Index("ix_rebalance_proposals_portfolio_created_at", "portfolio_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    portfolio_id: Mapped[UUID] = mapped_column(ForeignKey("portfolios.id"), nullable=False)
    recommendation_id: Mapped[UUID] = mapped_column(
        ForeignKey("recommendation_snapshots.id"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="PENDING")
    state_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    portfolio_value: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    cash_before: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    projected_cash: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    buy_total: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    sell_total: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    estimated_fees: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    fee_assumption: Mapped[str] = mapped_column(String(255), nullable=False)
    trades: Mapped[list] = mapped_column(JSON, nullable=False)
    resulting_weights: Mapped[list] = mapped_column(JSON, nullable=False)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


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


class DailyPrice(Base):
    """Cached daily OHLCV, adjusted with yfinance auto_adjust=True (splits and
    dividends; O/H/L/C on the same basis). Prices use unbounded NUMERIC so the
    Decimal values produced by market_data round-trip exactly."""

    __tablename__ = "daily_prices"

    __table_args__ = (
        UniqueConstraint("ticker", "date", name="uq_daily_price_ticker_date"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    date: Mapped[calendar_date] = mapped_column(Date, nullable=False)
    open: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class PriceCacheCoverage(Base):
    """Contiguous inclusive date range per ticker that has been fetched.
    Dates inside the range without a daily_prices row had no data (weekends,
    holidays, pre-listing) and are not re-requested."""

    __tablename__ = "price_cache_coverage"

    __table_args__ = (
        CheckConstraint(
            "covered_start <= covered_end",
            name="ck_price_cache_coverage_range",
        ),
    )

    ticker: Mapped[str] = mapped_column(String(20), primary_key=True)
    covered_start: Mapped[calendar_date] = mapped_column(Date, nullable=False)
    covered_end: Mapped[calendar_date] = mapped_column(Date, nullable=False)
    last_full_refresh_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )


class MLForecast(Base):
    """One stored ML forecast per ticker, forecast date, horizon and model
    version, written by the nightly job (scripts/nightly_jobs.py)."""

    __tablename__ = "ml_forecasts"
    __table_args__ = (
        UniqueConstraint(
            "ticker", "as_of", "horizon", "model_version", name="uq_ml_forecast_ticker_asof_horizon_version"
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    as_of: Mapped[calendar_date] = mapped_column(Date, nullable=False)  # latest feature date
    horizon: Mapped[int] = mapped_column(Integer, nullable=False)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    raw_forecast: Mapped[Decimal] = mapped_column(Numeric, nullable=False)  # horizon return, before clipping
    annual_forecast: Mapped[Decimal] = mapped_column(Numeric, nullable=False)  # clipped, annualized
    clipped: Mapped[bool] = mapped_column(Boolean, nullable=False)
    drivers: Mapped[list] = mapped_column(JSON, nullable=False)
    typical_estimate: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    training_start: Mapped[calendar_date] = mapped_column(Date, nullable=False)
    training_end: Mapped[calendar_date] = mapped_column(Date, nullable=False)
    training_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
