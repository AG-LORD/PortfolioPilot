"""Dashboard overview across a user's portfolios.

Each portfolio is valued with the regular valuation service. A price failure
(MarketDataUnavailableError) only marks that portfolio's valuation_status
"unavailable" with null value fields; the other portfolios and the response
still succeed. Value totals sum only portfolios valued "ok"
(valued_portfolio_count says how many); portfolio_count, initial_capital and
cash_balance cover every portfolio.
"""

import logging
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Holding, Portfolio, PortfolioSnapshot, RecommendationSnapshot, RiskProfile, Transaction
from app.schemas.overview import OverviewTotals, PortfolioOverviewItem, PortfolioOverviewRead
from app.schemas.recommendation import RecommendationSummary
from app.services.market_data import MarketDataUnavailableError
from app.services.valuation import get_portfolio_valuation

logger = logging.getLogger(__name__)

VALUATION_OK = "ok"
VALUATION_UNAVAILABLE = "unavailable"
SPARKLINE_POINTS = 30


def _latest_recommendations(db: Session, portfolio_ids: list[UUID]) -> dict[UUID, RecommendationSummary]:
    if not portfolio_ids:
        return {}
    snapshots = db.scalars(
        select(RecommendationSnapshot)
        .where(RecommendationSnapshot.portfolio_id.in_(portfolio_ids))
        .order_by(RecommendationSnapshot.portfolio_id, RecommendationSnapshot.created_at.desc())
    ).all()
    latest: dict[UUID, RecommendationSummary] = {}
    for snapshot in snapshots:
        if snapshot.portfolio_id not in latest:
            latest[snapshot.portfolio_id] = RecommendationSummary.model_validate(snapshot)
    return latest


def _sparklines(db: Session, portfolio_ids: list[UUID]) -> dict[UUID, list[Decimal]]:
    """total_value of each portfolio's last SPARKLINE_POINTS snapshots, oldest
    first; portfolios with fewer than 2 snapshots are left out."""
    if not portfolio_ids:
        return {}
    rows = db.execute(
        select(PortfolioSnapshot.portfolio_id, PortfolioSnapshot.total_value)
        .where(PortfolioSnapshot.portfolio_id.in_(portfolio_ids))
        .order_by(PortfolioSnapshot.portfolio_id, PortfolioSnapshot.snapshot_date.desc())
    ).all()
    newest_first: dict[UUID, list[Decimal]] = {}
    for portfolio_id, total_value in rows:
        values = newest_first.setdefault(portfolio_id, [])
        if len(values) < SPARKLINE_POINTS:
            values.append(total_value)
    return {pid: values[::-1] for pid, values in newest_first.items() if len(values) >= 2}


def _deposits(db: Session, portfolio_ids: list[UUID]) -> dict[UUID, Decimal]:
    """Net amount of every DEPOSIT transaction per portfolio (capital added after creation)."""
    if not portfolio_ids:
        return {}
    rows = db.execute(
        select(
            Transaction.portfolio_id,
            func.sum(Transaction.quantity * Transaction.price - Transaction.fees),
        )
        .where(Transaction.portfolio_id.in_(portfolio_ids), Transaction.transaction_type == "DEPOSIT")
        .group_by(Transaction.portfolio_id)
    ).all()
    return {pid: Decimal(str(total)) for pid, total in rows if total is not None}


def _sum_or_none(values: list[Decimal | None]) -> Decimal | None:
    present = [v for v in values if v is not None]
    return sum(present, Decimal("0")) if present else None


def get_portfolio_overview(db: Session, user_id: UUID) -> PortfolioOverviewRead:
    rows = db.execute(
        select(Portfolio, RiskProfile.category, func.count(Holding.id))
        .join(RiskProfile, RiskProfile.id == Portfolio.risk_profile_id)
        .outerjoin(Holding, Holding.portfolio_id == Portfolio.id)
        .where(Portfolio.user_id == user_id)
        .group_by(Portfolio.id, RiskProfile.category)
        .order_by(Portfolio.created_at)
    ).all()

    latest = _latest_recommendations(db, [portfolio.id for portfolio, _, _ in rows])
    sparklines = _sparklines(db, [portfolio.id for portfolio, _, _ in rows])
    deposits = _deposits(db, [portfolio.id for portfolio, _, _ in rows])

    portfolios = []
    for portfolio, category, holdings_count in rows:
        status = VALUATION_UNAVAILABLE
        market_value = total_value = unrealized_pnl = unrealized_pnl_pct = None
        try:
            valuation = get_portfolio_valuation(db, user_id, portfolio.id)
        except MarketDataUnavailableError as exc:
            logger.warning("Overview valuation unavailable for portfolio %s: %s", portfolio.id, exc)
        else:
            status = VALUATION_OK
            total_value = valuation.total_value
            market_value = valuation.total_value - valuation.cash_balance
            unrealized_pnl = valuation.unrealized_pnl
            # Relative to the cost basis of current holdings; undefined with none.
            if valuation.invested_value != 0:
                unrealized_pnl_pct = valuation.unrealized_pnl / valuation.invested_value

        portfolios.append(
            PortfolioOverviewItem(
                id=portfolio.id,
                name=portfolio.name,
                risk_category=category,
                initial_capital=portfolio.initial_capital,
                cash_balance=portfolio.cash_balance,
                valuation_status=status,
                market_value=market_value,
                total_value=total_value,
                unrealized_pnl=unrealized_pnl,
                unrealized_pnl_pct=unrealized_pnl_pct,
                holdings_count=holdings_count,
                latest_recommendation=latest.get(portfolio.id),
                total_deposited=portfolio.initial_capital + deposits.get(portfolio.id, Decimal("0")),
                updated_at=portfolio.updated_at,
                adopted_recommendation_id=portfolio.adopted_recommendation_id,
                adopted_at=portfolio.adopted_at,
                sparkline=sparklines.get(portfolio.id, []),
            )
        )

    valued = [p for p in portfolios if p.valuation_status == VALUATION_OK]
    totals = OverviewTotals(
        portfolio_count=len(portfolios),
        initial_capital=sum((p.initial_capital for p in portfolios), Decimal("0")),
        cash_balance=sum((p.cash_balance for p in portfolios), Decimal("0")),
        market_value=_sum_or_none([p.market_value for p in valued]),
        total_value=_sum_or_none([p.total_value for p in valued]),
        unrealized_pnl=_sum_or_none([p.unrealized_pnl for p in valued]),
        valued_portfolio_count=len(valued),
    )
    return PortfolioOverviewRead(totals=totals, portfolios=portfolios)
