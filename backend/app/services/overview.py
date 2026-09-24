"""Dashboard overview across a user's portfolios.

Valuation fields and latest_recommendation are not filled yet (always null,
valuation_status "unavailable"); only stored portfolio data is returned.
"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Holding, Portfolio, RiskProfile
from app.schemas.overview import OverviewTotals, PortfolioOverviewItem, PortfolioOverviewRead


def get_portfolio_overview(db: Session, user_id: UUID) -> PortfolioOverviewRead:
    rows = db.execute(
        select(Portfolio, RiskProfile.category, func.count(Holding.id))
        .join(RiskProfile, RiskProfile.id == Portfolio.risk_profile_id)
        .outerjoin(Holding, Holding.portfolio_id == Portfolio.id)
        .where(Portfolio.user_id == user_id)
        .group_by(Portfolio.id, RiskProfile.category)
        .order_by(Portfolio.created_at)
    ).all()

    portfolios = [
        PortfolioOverviewItem(
            id=portfolio.id,
            name=portfolio.name,
            risk_category=category,
            initial_capital=portfolio.initial_capital,
            cash_balance=portfolio.cash_balance,
            valuation_status="unavailable",
            market_value=None,
            total_value=None,
            unrealized_pnl=None,
            unrealized_pnl_pct=None,
            holdings_count=holdings_count,
            latest_recommendation=None,
        )
        for portfolio, category, holdings_count in rows
    ]

    totals = OverviewTotals(
        portfolio_count=len(portfolios),
        initial_capital=sum((p.initial_capital for p in portfolios), Decimal("0")),
        cash_balance=sum((p.cash_balance for p in portfolios), Decimal("0")),
        market_value=None,
        total_value=None,
        unrealized_pnl=None,
    )
    return PortfolioOverviewRead(totals=totals, portfolios=portfolios)
