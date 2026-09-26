from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Holding, Portfolio, RecommendationSnapshot, RiskProfile
from app.schemas.drift import DriftPositionRead, PortfolioDriftRead
from app.services import market_data
from app.services.market_data import MarketDataUnavailableError
from app.services.portfolios import get_portfolio

ZERO = Decimal("0")
CASH_TICKER = "CASH"


def get_portfolio_drift(
    db: Session,
    user_id: UUID,
    portfolio_id: UUID,
) -> PortfolioDriftRead:
    portfolio = get_portfolio(db, user_id, portfolio_id)
    risk_profile = db.get(RiskProfile, portfolio.risk_profile_id)
    holdings = db.scalars(
        select(Holding).where(Holding.portfolio_id == portfolio_id)
    ).all()
    target = db.scalars(
        select(RecommendationSnapshot)
        .where(RecommendationSnapshot.portfolio_id == portfolio_id)
        .order_by(RecommendationSnapshot.created_at.desc())
        .limit(1)
    ).first()

    target_weights = {
        item["ticker"]: Decimal(str(item["target_weight"]))
        for item in (target.allocations if target else [])
    }
    exclusions = {
        item["ticker"]: item["reason"]
        for item in (target.excluded if target else [])
    }

    prices: dict[str, Decimal] = {}
    missing_prices: list[str] = []
    for holding in holdings:
        try:
            prices[holding.ticker] = market_data.get_current_price(holding.ticker)
        except MarketDataUnavailableError:
            missing_prices.append(holding.ticker)

    valuation_complete = not missing_prices
    portfolio_value = (
        portfolio.cash_balance
        + sum((holding.quantity * prices[holding.ticker] for holding in holdings), ZERO)
        if valuation_complete
        else None
    )
    target_status = "missing"
    if target is not None:
        target_status = (
            "stale"
            if portfolio.updated_at > target.created_at
            else "current"
        )

    threshold = risk_profile.drift_threshold if risk_profile else ZERO
    positions_by_ticker = {holding.ticker: holding for holding in holdings}
    tickers = set(positions_by_ticker) | set(target_weights) | {CASH_TICKER}
    positions = []
    for ticker in sorted(tickers, key=lambda item: (item != CASH_TICKER, item)):
        holding = positions_by_ticker.get(ticker)
        if ticker == CASH_TICKER:
            current_value = portfolio.cash_balance
            quantity = None
            current_price = None
        elif holding is None:
            current_value = ZERO
            quantity = ZERO
            current_price = None
        elif ticker in prices:
            current_price = prices[ticker]
            current_value = holding.quantity * current_price
            quantity = holding.quantity
        else:
            current_price = None
            current_value = None
            quantity = holding.quantity

        current_weight = (
            current_value / portfolio_value
            if portfolio_value is not None and portfolio_value > ZERO and current_value is not None
            else None
        )
        if target is None:
            target_weight = None
        elif ticker == CASH_TICKER:
            target_weight = target.cash_weight
        else:
            target_weight = target_weights.get(ticker, ZERO)

        weight_difference = (
            current_weight - target_weight
            if current_weight is not None and target_weight is not None
            else None
        )
        if target is None:
            status = "no_target"
        elif weight_difference is None:
            status = "unavailable"
        elif abs(weight_difference) <= threshold:
            status = "at_target"
        elif weight_difference > ZERO:
            status = "overweight"
        else:
            status = "underweight"

        positions.append(
            DriftPositionRead(
                ticker=ticker,
                quantity=quantity,
                current_price=current_price,
                current_value=current_value,
                current_weight=current_weight,
                target_weight=target_weight,
                weight_difference=weight_difference,
                status=status,
                excluded=ticker in exclusions,
                exclusion_reason=exclusions.get(ticker),
                requires_attention=status in {"overweight", "underweight"},
            )
        )

    return PortfolioDriftRead(
        portfolio_id=portfolio_id,
        portfolio_value=portfolio_value,
        valuation_complete=valuation_complete,
        missing_prices=sorted(missing_prices),
        target_recommendation_id=target.id if target else None,
        target_created_at=target.created_at if target else None,
        target_status=target_status,
        drift_threshold=threshold,
        attention_count=sum(position.requires_attention for position in positions),
        positions=positions,
    )